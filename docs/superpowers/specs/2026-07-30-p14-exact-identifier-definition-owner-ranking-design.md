# P14 Exact-Identifier Definition-Owner Ranking v1 Design

Date: 2026-07-30
Status: Accepted on 2026-07-31 with an owner-approved probabilistic-model waiver
Repository: `/Users/flobby/vibe_coding/context-search-tool`
Behavior baseline: `501cf852ad54181eb823994747d2dc8555edc418`
Predecessors: P1 query-understanding acceptance, P8-P12 retrieval
experiments, and the P13 BGE provider implementation record
Companion plan:
`docs/superpowers/plans/2026-07-30-p14-exact-identifier-definition-owner-ranking.md`

The behavior baseline includes the committed OpenAI-compatible provider
and layered global/project configuration. P14 evaluates semantic
retrieval with SiliconFlow `Pro/BAAI/bge-m3` and evaluates the hybrid
profile with SiliconFlow `Qwen/Qwen2.5-14B-Instruct`. Local Ollama is not
an allowed live substitute. Both models, their API base URL, and
request counts are frozen before P14 production edits.

## Decision

Add a narrow, ranking-only rule for an exact code-identifier query:
when an already-recalled chunk declares that exact symbol, give it
stronger bounded evidence than chunks that merely reference the text.

P14 closes one concrete Phase 1 gap without reopening the rejected
P9-P12 mechanism families:

- it does not add a recall source or retrieve a symbol by a new lookup;
- it does not change graph expansion, relation quotas, final-selection
  capacity, planner configuration/algorithm, embeddings, or the frozen
  online provider identity;
- it does not special-case `INVOLVED_BY_ME`, Java, enum constants, or
  any repository path;
- it does not change the meaning of a prose query that happens to
  contain an identifier.

The selected mechanism is a bounded identifier sub-layer inside the
existing soft reranker:

```text
identifier_definition_owner_boost = 0.50
```

The value is frozen before implementation and live evaluation. It is
large enough, on the current diagnostic reports, to put the definition
owner near the top without creating a new hard rank tier or forcing it
above the most relevant business reference. It enters `_rerank_score`
only; it does not enter `_combined_score`, global normalization,
evidence classification, or protected-direct precedence.

## Evidence and Problem Boundary

### P13 result

P13 engineering readiness passed. BGE remains an opt-in provider
because the daily index ratio was `51.0428x`, just above the frozen
`50x` recommendation boundary. Provider-only quality improved:

- combined Recall@12: `0.859649 -> 0.877193`;
- newly satisfied required items: `1`;
- required losses: `0`;
- noise ratio: `0.712963 -> 0.708333`.

Both mandatory P1 profiles nevertheless remained at `6/7`.
`audit-status-literal` is their only failing required case.

### The remaining P1 miss

The query is exactly:

```text
INVOLVED_BY_ME
```

`INVOLVED_BY_ME` is a Java enum value declared by
`src/main/java/com/example/audit/AuditStatus.java`. It is not a
P14-specific token. The committed Java plugin already extracts enum
values as `SymbolRef(kind="enum_value")`, so the index already knows
which chunk declares the constant.

The locally retained reports show the following diagnostic ranks:

| profile | definition-owner rank | higher-ranked shape |
| --- | ---: | --- |
| `p1_vector_bge` | 5 | controller, executor, controller, service implementation |
| `p1_hybrid_bge` | 6 | controller, executor, controller, service implementation, mapper |

The owner itself has strong original evidence in both profiles. In the
vector report it has semantic `0.5354`, path/symbol `3.0`, direct text
`1.0`, and token coverage `1.0`; its generic role priority loses to
business-chain references. This is therefore an ordering gap, not an
acquisition gap.

Those retained `.quality/real-projects/p1-*.json` files identify an
older implementation commit, and P13's authoritative `/tmp` evidence
root is no longer present. They support the causal diagnosis only.
Task 0 attempts fresh baseline reports before production edits. If a
live dependency is unavailable, offline implementation may continue,
but Task 6 must capture from the immutable isolated baseline tree and
pass the baseline diagnostic before the first candidate live capture.
Task 6 also captures the paired real-corpus evidence. All artifacts
persist under a durable, gitignored `.quality/` root with recorded
SHA-256 values.

### Current query-understanding gap

`identifier_intent.py` recognizes camel/Pascal identifiers and
lowercase snake case. It deliberately ignores plain all-caps acronyms
such as `REST`, but it also misses SCREAMING_SNAKE identifiers such as
`INVOLVED_BY_ME`.

The current `identifier_exact_match_boost` is case-insensitive and
applies to path, symbol, or content occurrences. It correctly helps
identifier-shaped queries in general, but it cannot distinguish:

```text
enum AuditStatus { INVOLVED_BY_ME }   # declaration
if (status == INVOLVED_BY_ME)         # reference
```

P14 adds that missing distinction using existing declaration metadata.

### Closed mechanism families

P8 established that static declaration/structure facts are useful, but
its import-credit gate did not ship. P9/P9a/P10 exhausted relation-slot
membership rules, P11 exhausted indexed-vector overflow selection, and
P12 did not establish planner-hint membership as relevance. P14 does
not reopen any of them: its causal claim is only that the existing
ranker lacks a declaration-vs-reference feature for a pure identifier
query.

### Falsifiable hypothesis

On unchanged candidates, the full-query grammar plus a fixed `0.50`
owner feature will move `AuditStatus.java` into Top-3 in both fresh P1
profiles, preserve the other six required cases and the mixed endpoint
case, and create no non-eligible characterization or real-corpus loss.
Failure of any clause rejects P14 v1; it does not authorize a second
weight or predicate.

## Goals

1. Recognize a full-query SCREAMING_SNAKE identifier without
   reclassifying plain uppercase acronyms or mixed prose.
2. Represent whether the entire trimmed query is exactly one recognized
   identifier.
3. Distinguish an exact symbol declaration from a path/content
   reference using `DocumentChunk.symbols`.
4. Give exact definition owners a bounded, explainable advantage over
   text references while retaining the existing soft order.
5. Keep all non-exact query behavior unchanged, and prevent non-owner
   candidates from receiving the new owner feature.
6. Expose the owner feature through existing score parts, reasons, and
   RetrievalTrace v1 adjustments.
7. Close both P1 profiles at `7/7`, with `AuditStatus.java` within
   Top-3, without changing gold or quality thresholds.

## Non-Goals

- A global “go to definition” API.
- New symbol-table SQL, symbol recall, graph edges, or candidate
  expansion.
- Reference search, usage counting, canonical-owner inference, or
  duplicate-definition resolution.
- Parsing natural-language intent such as “definition of X” or “where
  is X used.”
- Quote/backtick normalization in v1.
- Case-insensitive definition ownership.
- Language-specific symbol-kind allowlists.
- A guarantee that the definition owner is Top-1.
- Changes to role weights, evidence classes, planner-ceiling
  protection, project-cohort semantics, or final-selection quotas.
- A special rule for uppercase content, enum constants, Java, or the
  P1 fixture.
- Any online-provider, default-provider, batching, or performance
  change.
- Repinning gold or widening an acceptance threshold after seeing the
  candidate result.

## Frozen Behavior Contract

### 1. Identifier grammar

P14 preserves the two existing identifier families and adds one
full-query-only family:

| family | grammar | positive examples | negative examples |
| --- | --- | --- | --- |
| camel/Pascal | existing `_CAMEL_OR_PASCAL_RE` | `useAuthStore`, `AuditStatus`, `HTTPServer` | `REST` |
| lowercase snake | existing `_SNAKE_IDENTIFIER_RE` | `apply_dev`, `restore_clean` | `apply_`, `_apply` |
| SCREAMING_SNAKE | `[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+` with `fullmatch(query.strip())` | `INVOLVED_BY_ME`, `HTTP_2_MODE` | `REST`, `INVOLVED_`, `_BY_ME` |

The underscore is mandatory for SCREAMING_SNAKE. This preserves the
existing exclusion of plain all-caps business words and acronyms.
Unlike the existing two search regexes, the new family writes only
`exact_identifier`; it is not appended to the shared `identifiers`
tuple. Ranking explicitly includes `exact_identifier` in its local
identifier-match inputs. This keeps ContextPack needs and exploration
goals on their existing identifier vocabulary. The existing
`identifiers` collection remains unique and lexicographically sorted.

`IdentifierIntent` gains:

```python
exact_identifier: str | None = None
```

`exact_identifier` is set iff:

1. `query.strip()` is non-empty;
2. that exact string is one recognized identifier match; and
3. the match spans the complete trimmed string.

Comparison is byte-for-byte Python string equality. P14 does not strip
backticks, quotes, punctuation, or explanatory words.

Examples:

| query | identifiers | exact identifier |
| --- | --- | --- |
| `INVOLVED_BY_ME` | `()` | `INVOLVED_BY_ME` |
| ` AuditStatus ` | `("AuditStatus",)` | `AuditStatus` |
| `apply_dev` | `("apply_dev",)` | `apply_dev` |
| `find INVOLVED_BY_ME` | `()` | `None` |
| `` `INVOLVED_BY_ME` `` | `()` | `None` |
| `REST` | `()` | `None` |
| `/apply/audit/pageEs INVOLVED_BY_ME` | `("pageEs",)` | `None` |

This distinction is the safety boundary. The mixed route-and-constant
P1 case retains its pre-existing `pageEs` camel identifier and
controller behavior, while gaining no `INVOLVED_BY_ME` intent.

### 2. Definition-owner eligibility

A chunk is a definition owner iff all of the following are true:

1. `intent.exact_identifier is not None`;
2. the chunk is already present in the merged candidate set;
3. at least one `chunk.symbols` entry has
   `symbol.name == intent.exact_identifier`;
4. the same symbol has
   `chunk.start_line <= symbol.start_line <= chunk.end_line`.

The symbol-name comparison is case-sensitive. Symbol kind and language
do not affect eligibility. Existing parsers own the meaning of
`DocumentChunk.symbols`; P14 neither reconstructs declarations from
content nor treats path/content matches as declarations.

The declaration-line condition is required because chunking attaches a
multi-line class/type `SymbolRef` to every overlapping chunk. Only the
chunk containing the declaration start is the owner for P14. Java enum
values already have a one-line `enum_value` symbol, so the target needs
no parser or index change.

P14 does not require the owner to be strong-original-direct. Instead,
the existing evidence class and planner-ceiling pass remain
authoritative: a planner-only or graph-only owner may carry the bounded
identifier score part, but it does not become protected and remains
subject to the existing ceiling. P14 v1 does not guess which of several
same-name declarations is canonical.

### 3. Bounded soft boost

The frozen score part is:

```python
identifier_definition_owner_boost = 0.50
```

`_identifier_intent_score_parts` writes the boost only for a definition
owner with no existing project-scope mismatch; on mismatch the key is
absent, not a positive but unapplied feature. For ranking only,
`_identifier_exact_match_score` evaluates the
ordered unique union of `intent.identifiers` and
`intent.exact_identifier`; this gives a pure SCREAMING_SNAKE query the
existing reference/path scores without exposing it to other consumers.
`_rerank_score` adds the owner part alongside that identifier sub-layer,
under the same project-scope guard:

```text
exact owner: existing identifier match 0.30 + owner boost 0.50
text reference: existing identifier match 0.20
```

The new `0.50` does not enter `_combined_score`, so it cannot change
global max normalization or every candidate's normalized score.
`pre_ceiling_rerank_score` does include the owner adjustment when the
existing project-scope guard permits it.

The feature is added before the existing second-pass planner ceiling.
P14 does not add a parallel counterfactual score or special ceiling
path. Consequently:

- an owner that participates in the existing strong-direct anchor can
  change the numeric ceiling;
- a non-strong owner remains subject to the resulting existing clamp;
- the existing multi-project cohort anchor consumes the post-ceiling
  rerank scores and may change, together with the existing penalties it
  induces; and
- the existing frontend cohort reranker may inspect a different subset
  of the ranked Top-10 files for an eligible exact query.

These are accepted downstream consequences of changing the ordinary
rerank score, not new policies. Focused tests must make the cascade
deterministic and must prove that the current ceiling rule, cohort
penalty, frontend scan Top-10, three-file read limit, 50,000-byte
per-file limit, sort keys, and final-selection policy are not modified.
P14 adds no I/O primitive or larger work cap, although an eligible exact
query may cause the existing frontend pass to read a different in-cap
set of files and may change which already-bounded context-expansion
reads follow the new order.

The feature does not mutate:

- acquisition score, pre-ranking merged candidate membership, or
  `combined_score`;
- `evidence_class`, `evidence_priority`, or `rank_tier`;
- any candidate source, semantic match, graph fact, or relation fact.

This value is a one-shot pre-committed hypothesis. The old P1 reports
predict:

| profile | diagnostic arithmetic | predicted rank |
| --- | --- | ---: |
| vector | `0.5908 + 0.30 + 0.50 = 1.3908` | 2 |
| hybrid | `0.4858 + 0.30 + 0.50 = 1.2858` | 2 |

The reports are directional, not authoritative new baselines. If fresh
evaluation does not meet Top-3, P14 v1 is rejected; the value is not
tuned after comparison.

### 4. Explanation and merge behavior

`_reasons` adds `exact identifier definition owner` whenever
`identifier_definition_owner_boost > 0`.

RetrievalTrace v1 needs no schema change:

- `identifier_definition_owner_boost` already matches the generic
  `_boost` adjustment convention;
- a ceiling clamp, when applicable, remains a separate existing
  adjustment;
- a scope-mismatched declaration has neither the boost key, reason, nor
  owner adjustment;
- the final numeric score and rank history use the normal final rerank
  score.

Context expansion may merge overlapping chunks from one file.
`identifier_definition_owner_boost` therefore joins the existing
winner-scoped score-part list. It must be copied from the same winning
expanded item as `rerank_score` and `reasons`; generic max-merging must
not attribute a loser's owner evidence to the winner.

No new span source is added. Definition ownership explains ordering,
not which recall source produced a visible source span.

### 5. Lifecycle summary

```text
raw query
  -> infer identifiers + exact_identifier
  -> existing candidate acquisition/merge
  -> owner witness from exact SymbolRef name + declaration line
  -> existing scoring + fixed owner boost
  -> existing evidence classification + planner ceiling
  -> existing project-cohort penalty
  -> existing frontend cohort rerank within Top-10 / 3 files / 50,000 bytes
  -> existing context expansion/final selection/trace
```

## Compatibility Invariants

1. If `exact_identifier is None`, ranking output is byte-for-byte
   unchanged.
2. For existing camel/Pascal/lower-snake families, an exact query with
   no applicable declaration-start witness is byte-for-byte unchanged;
   a project-scope-mismatched witness is not applicable.
3. A full-query SCREAMING_SNAKE term joins the existing
   ranking-local identifier scoring model: a content reference may
   receive its existing `0.20` and a path/symbol match its existing
   `0.30`, even when no owner is present. This is an eligible P14 delta;
   ContextPack/exploration identifier inputs remain unchanged.
4. A content/path occurrence without a matching declaration-start
   `SymbolRef` never gets the new `0.50` owner boost.
5. Case-mismatched declarations never qualify.
6. A class/type symbol that merely overlaps a later chunk qualifies
   only in the chunk containing `symbol.start_line`.
7. Planner-only and graph-only owners retain their existing evidence
   class, priority, and ceiling behavior.
8. Existing camel/Pascal and lowercase-snake reference boosts remain
   unchanged; their applicable exact whole-query declarations gain only
   the new bounded owner feature.
9. Plain uppercase acronyms such as `REST` remain unrecognized.
10. Candidate membership and recall-source counts do not change.
11. P3.1 trace schema, ContextPack schema, and public result schema do
   not change.
12. Hash and BGE use the identical P14 policy. No provider-specific
    branch is permitted.
13. Repeated calls and reversed candidate registration produce the
    same ordered results.
14. P14 does not change planner-ceiling, project-cohort, or frontend
    cohort algorithms or caps. Their numeric outputs and in-cap
    membership may change only for an eligible exact query because its
    rerank scores changed.

## Verification Contract

### Focused unit and pipeline matrix

The implementation must prove:

- SCREAMING_SNAKE full-match recognition and no mixed-query extraction;
- whole-query exactness, whitespace handling, and prose/backtick
  exclusion;
- plain-acronym exclusion;
- case-sensitive name and declaration-start-line ownership;
- a declaration moves ahead of enough stronger
  controller/service/test references to satisfy the bounded fixture,
  without a hard Top-1 assertion;
- content/path-only matches are references, not owners;
- a multi-chunk class/type symbol boosts only its declaration chunk;
- planner-only and graph-only owners remain unprotected and ceiling
  clamped when the existing contract requires it;
- generated/test/artifact and project-scope behavior is not bypassed;
- multi-project anchor/penalty cascades remain deterministic under the
  existing cohort algorithm;
- frontend cohort scanning stays within Top-10, three files, and 50,000
  bytes per file when the owner crosses that boundary;
- two same-name owners remain deterministic under reversed candidate
  registration;
- a non-exact prose query preserves its pre-P14 order and score parts;
- overlapping context expansion retains winner-consistent owner score
  parts, score, and reasons;
- trace shows `exact identifier definition owner` and the frozen `0.50`
  adjustment without a schema change.

### Protected behavior

Before implementation, enumerate every committed characterization and
quality query that satisfies the exact-query grammar. Record its family,
declaration-start witness, and project-scope applicability, then freeze
the inventory in the implementation evidence. Delta eligibility is:

- every full-query SCREAMING_SNAKE query is eligible for the new
  ranking-local `0.20`/`0.30` reference score and, where applicable,
  the owner feature;
- an exact camel/Pascal/lower-snake query is eligible only when at least
  one candidate has a case-sensitive declaration-start witness without
  project-scope mismatch; and
- every non-exact query, plus every existing-family exact query without
  such an applicable owner, must remain byte-for-byte unchanged.

Eligibility is frozen from the baseline evidence, never inferred from a
candidate delta.

The protected gates remain:

- retrieval-core boundary/import checks;
- P2 ContextPack, P3 trace, P4 exploration, P5 graph, P6 performance,
  and P7 selection suites;
- raw CI quality `8/8`;
- full non-slow suite under the repository-fixed runtime;
- no changes to frozen catalogs, gold, provider identities, or source
  snapshots.

### P1 closure

Run fresh live reports for both mandatory catalog profiles:

```text
p1_vector_bge
p1_hybrid_bge
```

The profile names are historical catalog identifiers. For P14 capture,
the external acceptance harness replaces only their runtime provider
sections in memory:

- embedding provider `openai-compatible`, model `Pro/BAAI/bge-m3`,
  dimensions `1024`, base URL `https://api.siliconflow.cn/v1`;
- hybrid planner provider `openai-compatible`, model
  `Qwen/Qwen2.5-14B-Instruct`, the same base URL, JSON response mode, and
  no fallback.

The catalog bytes, cases, gold, and thresholds remain unchanged. The
harness reads credentials from the user-level configuration, never
writes them into a derived catalog or evidence artifact, and rejects
any captured Ollama provider identity.

Required:

- both execute all seven required cases with no fallback/error/skip;
- both pass `7/7`;
- `audit-status-literal` places `AuditStatus.java` within Top-3;
- all other six cases remain pass;
- the existing focused pair gate remains unchanged and passes, including
  equal case/gate sets and hybrid MRR, Recall@5, and entrypoint-Top3 not
  below vector;
- catalog and thresholds are byte-identical to baseline.

`AuditStatus.java` at Top-1 is recorded as an observational result, not
a gate. The contract is deliberately no stronger than the committed
Top-3 requirement.

If either SiliconFlow model is unavailable, P1 closure is `BLOCKED`,
never inferred from unit tests, mocks, local Ollama, or cached reports.

### Real-corpus regression and cost

Use the frozen P8/P13 RedInk and daily repositories to capture baseline
and candidate under both `hash` and the frozen SiliconFlow
`Pro/BAAI/bge-m3` online provider.

For each provider:

- no required item may fall out of Top-12;
- Recall@12 may not decrease;
- Top-12 noise ratio may not increase;
- non-eligible cases—non-exact queries and existing-family exact
  queries without an applicable owner—must preserve canonical
  non-timing ranking output, including membership, order, score,
  score parts, and reasons;
- repeat captures must match after excluding declared timing and
  implementation fields.

For P1, repeat vector captures must have identical non-timing gate
inputs. Hybrid captures need identical case status, required ranks,
planner status, and fallback state; raw planner text is recorded but is
not required byte-identical because online generation can vary.

Because P14 adds no new I/O primitive, provider call, or candidate
source:

- online embedding request counts, static/descriptor embedding
  identities, base URL/model identities, selected-file counts, and
  structural counts must be identical;
- baseline query-p95 max/min spread must be `<= 0.15`;
- candidate/baseline median query p95 must be `<= 1.10`;
- no vector/manifest byte-identity claim is made because the existing
  capture schema does not expose those digests;
- any new store-read kind, filesystem-read primitive, network call,
  raised frontend read cap, or index schema change is a STOP. Existing
  frontend and context-expansion read membership/count may vary within
  their frozen limits for an eligible exact query.

For real-corpus timing, one complete paired rerun is permitted only when
the baseline stability gate fails. A second unstable baseline is
`BLOCKED`; the threshold is never widened. Non-timing vector drift is a
`STOP` for diagnosis, not a retry opportunity. For P1 hybrid
gate-input instability, retain every attempt and allow exactly one
complete baseline/candidate-pair rerun; a second instability is
`BLOCKED`. Never compare cherry-picked attempts. Raw planner text drift
alone is disclosed but is not a gate-input failure.

## Planned Change Surface

| action | path | responsibility |
| --- | --- | --- |
| modify | `src/context_search_tool/identifier_intent.py` | full-query SCREAMING_SNAKE and `exact_identifier` |
| modify | `src/context_search_tool/retrieval_core/ranking.py` | declaration witness, fixed owner boost, reason |
| modify | `src/context_search_tool/retrieval_core/context_expansion.py` | winner-scoped owner score parts |
| common prerequisite | `src/context_search_tool/query_planner.py` | apply identical whole-identifier rewrite suppression and original-identifier hint anchoring to baseline and candidate for online acceptance |
| modify | `tests/test_identifier_intent.py` | grammar and whole-query contract |
| modify | `tests/test_retrieval_pipeline.py` | ranking and expansion matrix |
| modify | `tests/test_retrieval_trace_pipeline.py` | adjustment/reason propagation |
| modify | `tests/test_retrieval_core_boundaries.py` | exact P14 reviewed production overlay |
| modify | `tests/test_exploration_boundaries.py` | exact P14 reviewed production overlay |
| conditional modify | `tests/test_retrieval_core_characterization.py` | selective P14 overlay for pre-inventoried exact queries only |
| modify | `tests/test_quality_p5.py` | explicit eligible protected-direct owner overlay |
| modify | `tests/test_p5_protected_direct.py` | explicit eligible protected-direct owner overlay |
| modify | `tests/test_p6_benchmark.py` | explicit eligible exact-query snapshot overlay |
| add | `tests/p14_definition_owner_acceptance.py` | reproducible P1/P8 gate-input comparison |
| add | `tests/test_p14_definition_owner_acceptance.py` | checker schema and outcome tests |
| modify | `tests/test_query_planner.py` | common prerequisite behavior and exact-identifier negative cases |
| conditional | `README.md`, `docs/retrieval-quality.md`, `roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md` | evidence-backed closure only |
| evidence | gitignored P14 run root | baseline/candidate captures and gate record |

The owner-ranking causal delta remains the first three production
files. `query_planner.py` is a common online-acceptance prerequisite and
is applied byte-identically to baseline and candidate, so it is not
credited to the ranking A/B result. No other production file is in
scope. If implementation requires another candidate source, parser,
storage, graph, provider, selection, or public-schema edit, stop and
revise the design before coding.

## Rejected Alternatives

### Special-case `INVOLVED_BY_ME` or enum constants

Reject. It would fit one benchmark and fail to express the actual
product rule.

### Add symbol recall

Reject for P14. The target owner is already rank 5/6. A recall change
would broaden candidate membership and confound the diagnosis.

### Increase the existing identifier boost

Reject. The current score intentionally applies to declarations,
references, paths, and content. Raising it cannot express ownership and
can strengthen the same higher-ranked references.

### Dynamic score floor above every reference

Reject. It would force Top-1 despite a Top-3 product requirement, make
the delta depend on unrelated candidates, and let one weak reference
inflate the owner score. The frozen `0.50` is a bounded one-shot
hypothesis within the existing identifier score scale.

### Add a definition tier to both sort keys

Reject for v1. It would change protected precedence semantics and
require a parallel field through ranking and context expansion. The
selected mechanism remains ordinary soft reranking with numeric score
and visible explanation aligned.

### Infer declarations from source text

Reject. Parsers already own symbol declarations. Regexing content would
confuse references, comments, strings, and generated text with owners.

### Promote identifiers embedded in prose

Reject for v1. “Find `X`,” “where is `X` used,” and “debug `X`” have
different intents. Exact whole-query syntax is the smallest defensible
contract.

## Risks and Mitigations

- **Common names have several declarations.** Promote every eligible
  declaration, retain existing deterministic tie-breakers, and make no
  canonical-owner claim.
- **A long-range type symbol appears in several chunks.** Require the
  symbol declaration start line to fall inside the owner chunk.
- **A parser emits an imprecise `SymbolRef`.** Require exact case and a
  declaration-line witness; parser correctness remains outside P14.
- **The fixed boost is too weak or too strong.** Freeze it before
  evaluation, use no Top-1 gate, and reject v1 rather than tune after
  comparison.
- **The value is benchmark-informed.** Treat P1 as closure of a known
  gap, not independent proof of universal quality; require
  language-neutral synthetic witnesses, the pre-inventoried
  characterization set, and zero-loss hash/online real-corpus gates.
- **A merge attributes the wrong boost.** Treat the new part as
  winner-scoped and test both winner/loser directions.
- **The score change cascades through existing downstream rank
  consumers.** Accept numeric ceiling/cohort and in-cap frontend-read
  changes only for eligible exact queries; freeze the existing
  algorithms/caps and test multi-project and Top-10 boundary cases.
- **The targeted fix regresses normal queries.** Gate on whole-query
  exactness, freeze the eligible-query inventory before edits, and
  require non-eligible capture parity.
- **The live dependency is unavailable.** Complete offline correctness
  work, but leave P1 and the final ship disposition BLOCKED. Do not
  fall back to Ollama.
- **The shared checkout contaminates evidence.** Implement and capture
  from the isolated online-baseline and candidate worktrees; audit
  tracked and untracked paths at every checkpoint.

## Final Acceptance Amendment and Record

On 2026-07-31 the definition owner explicitly accepted bounded online
model variance as probabilistic behavior rather than a product failure.
After the owner-directed switch from Ollama to the approved online Pro
embedding and 14B planner, this amendment authorizes three bounded
acceptance changes: the common `query_planner.py` prerequisite above,
an online stable projection that masks declared continuous model-score
fields while retaining membership/order/rank and evidence categories,
and an exact hybrid MRR tolerance of `1/42` (one of seven cases moving
from rank 2 to rank 3 while remaining inside the Top-3 contract).
Recall@5 and entrypoint Top-3 retain zero automated tolerance. The one
observed rank-4 result exceeds the automatic tolerance and is accepted
only by the separate owner waiver. None of these changes modifies the
frozen identifier grammar, the `0.50` owner boost, catalog, gold,
retrieval caps, or raw evidence. The strict machine reports remain
immutable and are paired with separately hashed owner-acceptance files.

The accepted online-drift boundary is outcome based:

- continuous embedding/rerank values, auxiliary planner hints, and
  same-path chunk-derived score evidence may vary;
- a near-tie order may vary when selected membership, protected winner,
  required coverage, Recall, noise, structure, request counts, and the
  performance envelope remain safe;
- wrong provider/model identity, Ollama substitution, fallback, error,
  skip, required loss, recall decrease, noise increase, protected-winner
  change, selected-membership loss, structural/request drift, or a
  candidate/baseline query-p95 ratio above `1.10` is not waived.

The final live runtime was SiliconFlow
`openai-compatible/Pro/BAAI/bge-m3` at 1024 dimensions plus
`openai-compatible/Qwen/Qwen2.5-14B-Instruct`. Embedding calls used a
240,000-token sliding-minute budget, an 80,000-token request budget, a
two-second minimum interval, singleton P1 requests, and bounded greedy
P8 batches. P8 children isolated the project hash configuration from
the user global provider config while reading online credentials from
the explicitly validated provider-config path.

Final evidence is under
`.quality/p14-runs/20260731T080504Z-online-pro-business-stable/`:

- P8 completed all eight hash/online captures. Hash recall remained
  `49/57`; online recall remained `50/57`; required losses were zero;
  online noise stayed `153/216`; selected membership matched for all 18
  cases; the online timing ratio was `1.0036899347718384`; and each
  online capture made 92 calls without a 429. The strict report is
  `p8-final/gates.json` (`reject` for exact repeat/parity rules), while
  `p8-final/owner-acceptance.json` records the accepted `ship` outcome
  and preserves the strict report hash.
- P1 vector candidate repeats were both `7/7`, with owner ranks `[2,2]`.
  Hybrid repeats were `6/7` and `7/7`, with owner ranks `[4,3]`,
  Recall@5 `1.0` in both, 14/14 planner calls `ok`, zero fallback/error/
  skip, and no exact-identifier rewrite. The strict report is
  `p1-final-v4/gates.json` (`blocked` for the Top-3/MRR/hint-determinism
  rules), while `p1-final-v4/owner-acceptance.json` records the accepted
  `ship` outcome and preserves the strict report hash.

The online captures bind candidate commit
`adbee96a342d80a7cce0d26d562c83d282d6646c` plus tracked-diff SHA-256
`5dc7a5a191e197c8fd7452382099391807530cdfbdfc0641ac9270a93c1ab87a`.
Independent review then requested a test-only planner grammar matrix. The
current candidate tracked-diff SHA-256 is
`2eb54eed82b931108bc65a10fb5d5407d8e58ab0bf157dc0bc620d660ea91a8b`;
the current shared-baseline SHA-256 is
`aa59a239614d611cd64dc9353fdc4e3871a169123c5f08746a7046bd2bd1dbf6`.
The old and new production `src` tree are both
`606dd06f82bce27ec6f1f3146819113c6ee414e2`; only
`tests/test_query_planner.py` changed after capture, identically on both
sides. Post-review regression is 136 acceptance/planner tests, 46 planner
tests per side, and one clean-tree full run of `3411 passed, 9 skipped`.
Parallel Standards and Spec review has no remaining blocker/high/medium
finding. The self-contained `final-acceptance-manifest.json` maps and
verifies 23 evidence artifacts; its SHA-256 is
`16a210efb9bfff3d4322932fe180a14bbcb1fada9275e8bc74685424db947608`.

Final disposition: `ship` by explicit owner acceptance, with every raw
strict failure retained and auditable.

## Acceptance Summary

The original strict checklist below remains the machine-policy history.
The final disposition applies the owner-approved probabilistic-model
amendment above:

1. the identifier, planner whole-query, and owner contracts are fully tested;
2. the three owner-ranking production files and the byte-identical shared
   planner prerequisite are the only production changes;
3. non-eligible selected membership and protected winners remain unchanged;
   declared near-tie online order/evidence drift is owner-waived;
4. protected/full suites pass;
5. vector P1 passes `7/7` twice; hybrid is `6/7` and `7/7`, with its one
   rank-4 result separately owner-waived while Recall@5 remains `1.0`;
6. both provider real-corpus comparisons have zero required loss and no
   noise or query-p95 gate failure;
7. an independent Standards + Spec review has no blocking finding;
8. the implementation record reports evidence and disposition before
   any product/roadmap claim.
