from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from context_search_tool.graph_contract import (
    MAX_TEST_TARGETS_PER_FILE,
    generate_v5_relation_id,
)
from context_search_tool.models import CodeRelation, CodeSignal, SourceFile
from context_search_tool.test_paths import (
    is_forbidden_test_target_path,
    is_test_path,
    production_candidates_for_test,
)


_PRODUCER = "test_association"
_RESOLVED = frozenset({"resolved_exact", "resolved_unique"})
_IMPORT_KINDS = frozenset({"imports", "imports_type"})


@dataclass(frozen=True)
class TestAssociationSnapshot:
    __test__ = False

    source_files: tuple[SourceFile, ...]
    signals: tuple[CodeSignal, ...]
    resolved_relations: tuple[CodeRelation, ...]


@dataclass(frozen=True)
class _Evidence:
    target: CodeSignal
    basis: str
    confidence: float
    source_line: int
    source_column: int
    provenance_relation_id: str
    occurrence_count: int = 1


class TestAssociationSession(Protocol):
    def snapshot(self) -> TestAssociationSnapshot: ...

    def replace_test_associations(
        self,
        relations: tuple[CodeRelation, ...],
        *,
        producer_resolution_generation: int,
    ) -> None: ...


class TestAssociationStore(Protocol):
    def test_association_session(
        self,
    ) -> AbstractContextManager[TestAssociationSession]: ...


def build_test_associations(
    *,
    source_files: Iterable[SourceFile],
    signals: Iterable[CodeSignal],
    resolved_relations: Iterable[CodeRelation],
) -> tuple[CodeRelation, ...]:
    files = tuple(source_files)
    signal_rows = tuple(signals)
    import_rows = tuple(resolved_relations)
    files_by_path = {file.path: file for file in files}
    signals_by_id = {signal.signal_id: signal for signal in signal_rows}
    modules_by_path = _unique_modules_by_path(signal_rows)

    relations_by_source: dict[str, list[CodeRelation]] = {}
    for relation in import_rows:
        if (
            relation.kind in _IMPORT_KINDS
            and relation.resolution in _RESOLVED
            and relation.target_signal_id
        ):
            relations_by_source.setdefault(relation.source_signal_id, []).append(
                relation
            )

    output: list[CodeRelation] = []
    for source_path, source_module in sorted(
        modules_by_path.items(), key=lambda item: item[0].as_posix()
    ):
        source_file = files_by_path.get(source_path)
        if source_file is None or not _is_test_file(source_file, source_module):
            continue
        evidence: dict[str, _Evidence] = {}
        for item in _explicit_import_evidence(
            source_module=source_module,
            relations=relations_by_source.get(source_module.signal_id, []),
            signals_by_id=signals_by_id,
            modules_by_path=modules_by_path,
            files_by_path=files_by_path,
        ):
            _retain_strongest(evidence, item)
        convention = _convention_evidence(
            source_file=source_file,
            source_module=source_module,
            modules_by_path=modules_by_path,
            files_by_path=files_by_path,
        )
        if convention is not None:
            _retain_strongest(evidence, convention)

        selected = sorted(
            evidence.values(),
            key=lambda item: (
                -item.confidence,
                item.source_line,
                item.source_column,
                item.target.file_path.as_posix(),
                item.target.signal_id,
            ),
        )[:MAX_TEST_TARGETS_PER_FILE]
        output.extend(_test_relation(source_module, item) for item in selected)
    output.sort(
        key=lambda item: (
            item.source_signal_id,
            item.target_project_unit_key,
            item.target_qualified_name,
            item.relation_id,
        )
    )
    return tuple(output)


generate_test_associations = build_test_associations


def regenerate_test_associations(
    store: TestAssociationStore,
    *,
    producer_resolution_generation: int,
) -> tuple[CodeRelation, ...]:
    with store.test_association_session() as session:
        snapshot = session.snapshot()
        relations = build_test_associations(
            source_files=snapshot.source_files,
            signals=snapshot.signals,
            resolved_relations=snapshot.resolved_relations,
        )
        session.replace_test_associations(
            relations,
            producer_resolution_generation=producer_resolution_generation,
        )
    return relations


def _unique_modules_by_path(
    signals: tuple[CodeSignal, ...],
) -> dict[Path, CodeSignal]:
    candidates: dict[Path, list[CodeSignal]] = {}
    for signal in signals:
        if signal.kind == "module" and signal.producer == "core_module":
            candidates.setdefault(signal.file_path, []).append(signal)
    return {
        path: values[0]
        for path, values in candidates.items()
        if len(values) == 1
    }


def _is_test_file(file: SourceFile, module: CodeSignal) -> bool:
    return is_test_path(
        file.path,
        file.language,
        module.project_unit_key,
    )


def _explicit_import_evidence(
    *,
    source_module: CodeSignal,
    relations: list[CodeRelation],
    signals_by_id: dict[str, CodeSignal],
    modules_by_path: dict[Path, CodeSignal],
    files_by_path: dict[Path, SourceFile],
) -> tuple[_Evidence, ...]:
    output: list[_Evidence] = []
    for relation in sorted(
        relations,
        key=lambda item: (
            int(item.metadata.get("first_source_line", 0)),
            int(item.metadata.get("first_source_column", 0)),
            item.kind,
            item.target_signal_id,
            item.relation_id,
        ),
    ):
        target_signal = signals_by_id.get(relation.target_signal_id)
        if target_signal is None:
            continue
        target_module = (
            target_signal
            if target_signal.kind == "module"
            else modules_by_path.get(target_signal.file_path)
        )
        if target_module is None or not _legal_target(
            source_module,
            target_module,
            files_by_path,
        ):
            continue
        output.append(
            _Evidence(
                target=target_module,
                basis="exact_test_import",
                confidence=1.0,
                source_line=int(relation.metadata.get("first_source_line", 0)),
                source_column=int(
                    relation.metadata.get("first_source_column", 0)
                ),
                provenance_relation_id=relation.relation_id,
                occurrence_count=max(
                    1,
                    int(relation.metadata.get("occurrence_count", 1)),
                ),
            )
        )
    return tuple(output)


def _convention_evidence(
    *,
    source_file: SourceFile,
    source_module: CodeSignal,
    modules_by_path: dict[Path, CodeSignal],
    files_by_path: dict[Path, SourceFile],
) -> _Evidence | None:
    legal: dict[str, CodeSignal] = {}
    for candidate_path in production_candidates_for_test(
        source_file.path,
        source_file.language,
        source_module.project_unit_key,
    ):
        candidate = modules_by_path.get(candidate_path)
        if candidate is None or not _legal_target(
            source_module,
            candidate,
            files_by_path,
        ):
            continue
        legal[candidate.signal_id] = candidate
    if len(legal) != 1:
        return None
    [target] = legal.values()
    return _Evidence(
        target=target,
        basis="exact_test_path",
        confidence=0.95,
        source_line=source_module.start_line,
        source_column=source_module.start_column,
        provenance_relation_id="",
    )


def _legal_target(
    source_module: CodeSignal,
    target_module: CodeSignal,
    files_by_path: dict[Path, SourceFile],
) -> bool:
    target_file = files_by_path.get(target_module.file_path)
    if target_file is None:
        return False
    if target_module.project_unit_key != source_module.project_unit_key:
        return False
    if target_file.is_generated or is_forbidden_test_target_path(target_file.path):
        return False
    if is_test_path(
        target_file.path,
        target_file.language,
        target_module.project_unit_key,
    ):
        return False
    return target_module.signal_id != source_module.signal_id


def _retain_strongest(
    evidence: dict[str, _Evidence], item: _Evidence
) -> None:
    existing = evidence.get(item.target.signal_id)
    if existing is None:
        evidence[item.target.signal_id] = item
        return
    selected = item if _evidence_key(item) < _evidence_key(existing) else existing
    occurrence_count = selected.occurrence_count
    if item.basis == existing.basis and item.confidence == existing.confidence:
        occurrence_count = existing.occurrence_count + item.occurrence_count
    evidence[item.target.signal_id] = _Evidence(
        target=selected.target,
        basis=selected.basis,
        confidence=selected.confidence,
        source_line=selected.source_line,
        source_column=selected.source_column,
        provenance_relation_id=selected.provenance_relation_id,
        occurrence_count=occurrence_count,
    )


def _evidence_key(item: _Evidence) -> tuple[object, ...]:
    return (
        -item.confidence,
        item.source_line,
        item.source_column,
        item.basis,
        item.provenance_relation_id,
    )


def _test_relation(source: CodeSignal, evidence: _Evidence) -> CodeRelation:
    target = evidence.target
    relation_id = generate_v5_relation_id(
        source_signal_id=source.signal_id,
        kind="tests",
        target_kind="module",
        target_qualified_name=target.qualified_name,
        target_signature="",
        target_arity=None,
        target_project_unit_key=target.project_unit_key,
        producer=_PRODUCER,
    )
    metadata: dict[str, object] = {
        "selector_state": "exact",
        "resolution_basis": evidence.basis,
        "candidates": (target.qualified_name,),
        "first_source_line": evidence.source_line,
        "first_source_column": evidence.source_column,
        "occurrence_count": evidence.occurrence_count,
    }
    if evidence.provenance_relation_id:
        metadata["provenance_relation_id"] = evidence.provenance_relation_id
    return CodeRelation(
        relation_id=relation_id,
        source_signal_id=source.signal_id,
        target_name=target.file_path.as_posix(),
        kind="tests",
        confidence=1.0,
        metadata=metadata,
        target_kind="module",
        target_qualified_name=target.qualified_name,
        target_project_unit_key=target.project_unit_key,
        resolution="unresolved",
        producer=_PRODUCER,
        producer_confidence=1.0,
    )
