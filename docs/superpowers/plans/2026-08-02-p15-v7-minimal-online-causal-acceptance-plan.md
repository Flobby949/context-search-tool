# P15-v7 Minimal Online Causal Acceptance Plan

Status: DRAFT. `execution_eligible=false`; a single user approval receipt is
required before Tasks 1–6 may run.

Companion design:
`docs/superpowers/specs/2026-08-02-p15-v7-minimal-online-causal-acceptance-design.md`.

## Corrected two-repository execution boundary

The sealed full catalog remains auditable evidence, but only its first two
distinct repositories in canonical pre-ref order are selected for resolution.
For each selected repository, issue the identical ref request at most three
times, with a 30-second timeout per attempt and fixed backoff `[0, 2, 5]`.
Record every attempt. Three failures produce `INCONCLUSIVE`; do not call or
substitute a third repository. A catalog with fewer than two distinct prefix
entries fails before any command call.

The DRAFT contract is not execution eligible and keeps all external counters at
zero. One future user approval receipt covers the continuous sequence: two refs,
source access, fresh execution, and—if fresh passes—held-out plus release. It is
not split into four approvals. Any plan field, threshold, query, model, or
case-rule change requires reapproval before continuing.

## Success criteria for this DRAFT correction

This correction succeeds when both P15-v7 documents state the same corpus,
sampling, outcome, held-out, performance, privacy, governance, prefix-two, retry,
and approval rules; the acceptance harness proves them using an injected fake
command runner; and no real ref, source, online model, Ollama, or held-out
operation occurs. Record the document, contract, receipt, runner, validator, and
test SHA-256 values and stop with the contract still in DRAFT.

## Task 0 — Freeze the v7 design and plan documents

**Authorized files only:**

- `docs/superpowers/specs/2026-08-02-p15-v7-minimal-online-causal-acceptance-design.md`
- `docs/superpowers/plans/2026-08-02-p15-v7-minimal-online-causal-acceptance-plan.md`

Verify statically:

1. one future authoritative attempt contract is named;
2. outcome, release, and governance are separate;
3. fresh corpus is two repositories times six cases: four efficacy and two guard
   cases per repository;
4. only eight target-missing efficacy cases form the primary denominator;
5. queries are source-only and gold comes from independent direct-import AST;
6. selection uses only structure and control target absence;
7. source exact match, planner status, candidate admissibility, private helpers,
   and gold-first-two never delete or select a case;
8. every query has two real SiliconFlow Qwen samples, one planner call per
   sample, with the exact validated/fallback plan and pre-treatment state shared
   by local control/treatment replay;
9. every `sample × arm` has exactly two local replays in the complete
   pre-result frozen schedule, with no result-dependent append;
10. cross-sample Top12 may differ while same-sample local replay is exact;
11. all cases and samples run before disposition;
12. fresh, held-out, performance, privacy, and ship gates match the design; and
13. old oracle recovery, candidate-conditioned eligibility, cross-sample exact
    equality, and legacy safety-harness construction are removed.

After static verification, keep Tasks 1–6 blocked on the single approval receipt.

## Task 1 — Future authoritative contract binding

**Not currently authorized. Future file:**
`tests/fixtures/p15_v7_minimal_online_causal/attempt-contract.json`.

Create one contract with separate `identity`, `corpus`, `sampling`, `outcome`,
`release`, and `governance` sections. In `pre_corpus_frozen`, bind:

- attempt ID and baseline/candidate product projections;
- the sole `consume_dependency_hints` factor;
- SiliconFlow provider/endpoints, Qwen and embedding models, prompt and schema;
- the complete fixed sampling identity: repository/case/sample/arm/replay order,
  exactly two samples per query, exactly one planner call per sample, exactly two
  local replays per arm, and the finite slot cardinalities;
- TopK, budgets, caps, privacy payload, and zero localhost/Ollama policy;
- independent AST/query/corpus rules;
- the complete fresh and held-out outcome gates;
- performance, test, CI, and artifact privacy release gates; and
- the held-out public contract and sealed-payload digest.

The future validator must reject an outcome or run-local document that supplies
a gate absent from this contract. It must not become a new general-purpose
security harness.

Verify: a canonical projection of every non-corpus field is frozen before any
fresh identity or source access.

## Task 2 — Future candidate-blind corpus binding

**Not currently authorized.**

Use exactly the two resolved canonical-prefix repositories. For each repository
in order:

1. bind URL, commit, license, inventory, and source content projection;
2. generate the stable independent-AST direct-import pool;
3. before any online request, freeze exactly structural indices 1–6;
4. assign indices 1–2 to guard and indices 3–6 to efficacy;
5. make zero online qualification requests and never scan index 7 or later; and
6. forbid case and repository replacement.

Run the complete two-sample matrix for all twelve frozen cases. If either
control sample contains an efficacy candidate's gold target, finish all 24
online samples and 96 local arm replays, then emit `INCONCLUSIVE_CORPUS`. Do not
stop early, scan further, or substitute a case or repository.

Append exact repository, case, control-sample, shared-state, query, gold, and
denominator hashes to the same authoritative contract. Revalidate that every
pre-corpus field is unchanged, set `sealed_before_candidate`, and freeze the
fully expanded finite case/sample/arm/replay schedule and final contract SHA.
The schedule must be complete before treatment output and may not be extended,
retried, or replaced after any result is read.

Verify: exactly 12 total cases in frozen order, exactly 4 efficacy candidates
and 2 guards per repository, `qualification_online_requests=0`, and no treatment
execution before the manifest is sealed.

## Task 3 — Future complete same-plan paired execution

**Not currently authorized.**

For every one of 12 cases and both frozen samples:

1. use the already bound real SiliconFlow Qwen response or bound fallback;
2. load the exact shared embedding/index/base-roster state;
3. locally replay control and treatment from that same state;
4. execute each local arm exactly twice in its prebound order and require exact
   same-sample normalized projections across those two replays;
5. record target membership/rank, rank-1, relevance/noise, exact witness,
   request counts, local latency, and end-to-end online latency; and
6. continue until all 24 paired samples and all 96 scheduled local arm replays
   complete, regardless of intermediate success or failure.

No candidate-side planner or embedding request is allowed. A provider outage
that prevents the frozen matrix is `blocked`; no model, repo, query, or endpoint
substitution is allowed. No result-dependent replay, retry, extra sample,
replacement slot, or schedule append is allowed.

## Task 4 — Future fresh outcome decision

**Not currently authorized.**

Compute outcome only from the eight efficacy targets, while applying loss,
rank-1, noise, determinism, privacy, and latency safety to all twelve cases.

Pass fresh efficacy only if:

- at least 3 stable causal new targets across 3 efficacy cases;
- each repository contributes at least 1 stable causal gain;
- required target losses are 0;
- rank-1 changes are 0;
- every gain has a closed exact witness;
- valid plans are at least 22 of 24, with fallback retained in denominator;
- aggregate Precision@12 decline is at most 0.02; and
- at most 1 treatment-only irrelevant `(case, sample, path)` appears.

Report control/treatment target Recall@12 and delta without a separate Recall
pass threshold. Do not stop or repeat selectively based on first results.

## Task 5 — Future conditional held-out

**Not currently authorized.**

Only after fresh outcome passes under the same single approval receipt, verify
the bound held-out seal and open one independently selected Python repository with at
least four candidate-blind target-missing efficacy cases. Use the same
source-only query, independent AST gold, two online samples, fallback retention,
shared-plan replay, exactly two local replays per arm, prebound order, and exact
local determinism rules. The sealed payload contains the complete finite
held-out schedule; opening cannot add a slot.

Held-out passes with at least two stable causal gains across two cases and zero
required target loss. Opening forbids later candidate, model, prompt, schema,
case, query, gold, threshold, or denominator changes.

## Task 6 — Future release and governance decision

**Not currently authorized.**

Evaluate release independently from efficacy:

- zero candidate-added online requests;
- shared-plan local median regression at most 10%, or absolute increase at most
  5 ms;
- end-to-end online latency reported only;
- planner payload query-only plus frozen numeric limits;
- frozen SiliconFlow identities and zero localhost/Ollama requests;
- zero secret, authorization-header, source-body, absolute-path, or raw-exception
  leakage in evidence/logs;
- unchanged TopK, caps, and budgets; and
- focused tests, full suite, and CI pass.

Then emit one of `ship`, `accept_outcome`, `reject_outcome`, `release_reject`, or
`blocked` exactly as defined by the design. A release failure must not overwrite
or relabel a valid efficacy result.

## Stop condition

For the current revision, stop after DRAFT hashes and local fake-runner gates are
recorded. The next permitted action, only after the single user approval receipt,
is the continuous Tasks 1–6 sequence. No ref call, source access, online model,
Ollama, fresh execution, or held-out opening is part of this DRAFT revision.
