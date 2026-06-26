from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class QueryIntent:
    operations: frozenset[str] = field(default_factory=frozenset)
    target_roles: frozenset[str] = field(default_factory=frozenset)
    artifact_roles: frozenset[str] = field(default_factory=frozenset)
    wants_artifact: bool = False
    confidence: int = 0


_OPERATION_KEYWORDS = {
    "save": {"save", "saving", "persist", "persistence", "保存", "持久化", "存储"},
    "update": {"update", "modify", "edit", "更新", "修改"},
    "delete": {"delete", "remove", "删除", "移除"},
    "download": {"download", "zip", "export", "下载", "导出", "打包"},
    "scan": {"scan", "sync", "synchronize", "扫描", "同步"},
    "generate": {"generate", "生成", "创建"},
    "retry": {"retry", "regenerate", "重试", "重新生成"},
}

_TARGET_ROLE_KEYWORDS = {
    "entrypoint": {"api", "endpoint", "route", "router", "controller", "接口", "路由"},
    "implementation": {"service", "handler", "logic", "impl", "实现", "逻辑", "服务"},
    "ui": {"page", "view", "component", "form", "store", "页面", "表单", "组件"},
    "config": {"config", "setting", "settings", "yaml", "yml", "配置", "服务商"},
    "deploy": {"docker", "compose", "deployment", "deploy", "部署", "容器"},
    "history": {"record", "records", "历史记录"},
    "test": {"test", "spec", "测试"},
    "doc": {"doc", "docs", "readme", "文档", "说明"},
}

_ARTIFACT_KEYWORDS = {
    "config_artifact": {
        "yaml",
        "yml",
        "json",
        "toml",
        "docker",
        "compose",
        "dockerfile",
        "配置文件",
    },
    "generated_artifact": {"output", "dist", "build", "生成文件", "产物"},
    "doc_artifact": {"readme", "docs", "markdown", "文档"},
    "test_artifact": {"test", "spec", "测试"},
}

_ARTIFACT_REQUEST_HINTS = {
    "file",
    "files",
    "artifact",
    "artifacts",
    "docker",
    "compose",
    "deployment",
    "deploy",
    "readme",
    "docs",
    "文件",
    "配置文件",
    "部署",
    "文档",
    "产物",
}


def infer_query_intent(query: str, tokens: list[str]) -> QueryIntent:
    raw = query.lower()
    terms = {token.lower() for token in tokens if token}
    raw_terms = set(re.findall(r"[a-z0-9_]+", raw))
    operations = _matching_groups(raw, raw_terms, terms, _OPERATION_KEYWORDS)
    target_roles = _matching_groups(raw, raw_terms, terms, _TARGET_ROLE_KEYWORDS)
    artifact_roles = _matching_groups(raw, raw_terms, terms, _ARTIFACT_KEYWORDS)
    wants_artifact = bool(
        artifact_roles
        and (
            _has_any(raw, raw_terms, terms, _ARTIFACT_REQUEST_HINTS)
            or target_roles.intersection({"deploy", "doc", "test"})
        )
    )
    confidence = len(operations) + len(target_roles) + (1 if wants_artifact else 0)
    return QueryIntent(
        operations=frozenset(operations),
        target_roles=frozenset(target_roles),
        artifact_roles=frozenset(artifact_roles),
        wants_artifact=wants_artifact,
        confidence=confidence,
    )


def _matching_groups(
    raw: str,
    raw_terms: set[str],
    terms: set[str],
    groups: dict[str, set[str]],
) -> set[str]:
    matches: set[str] = set()
    for group, keywords in groups.items():
        if _has_any(raw, raw_terms, terms, keywords):
            matches.add(group)
    return matches


def _has_any(
    raw: str,
    raw_terms: set[str],
    terms: set[str],
    keywords: set[str],
) -> bool:
    for keyword in keywords:
        lowered = keyword.lower()
        if _is_cjk_keyword(lowered):
            if lowered in raw:
                return True
            continue
        if lowered in terms or lowered in raw_terms:
            return True
    return False


def _is_cjk_keyword(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)
