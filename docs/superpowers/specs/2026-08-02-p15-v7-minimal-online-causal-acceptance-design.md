# P15-v7 Minimal Online Causal Acceptance Design

Status: DRAFT. `execution_eligible=false`; a single user approval receipt is
required before any ref, source, fresh-model, held-out, or release execution.

## 0. Two-repository correction and approval boundary

The already sealed 130-entry catalog remains the complete auditable catalog
evidence. It is not a ref-resolution work queue. Resolution selects exactly the
first two distinct repositories in the sealed canonical pre-ref order. No third
or later catalog repository may be called or substituted.

Each selected repository has exactly three attempts of the identical
`git ls-remote` request, each with a 30-second timeout and fixed backoff
`[0, 2, 5]` seconds. Every attempt is recorded. Exhausting the three attempts
ends the attempt as `INCONCLUSIVE`; it never advances to a third repository.

The current contract remains DRAFT, is not execution eligible, requires user
approval, and retains zero ref/source/model/Ollama/held-out counters. One future
approval receipt authorizes the continuous sequence: resolve the two refs,
access their source, run fresh acceptance, and—only if fresh passes—open held-out
and evaluate release. There are no additional approval gates inside that
sequence. Any plan field, threshold, query, model, or case-rule change invalidates
the receipt and requires reapproval.

## 1. Decision

P15-v7 evaluates one claim: when the same validated or fallback online planner
result and the same pre-treatment retrieval state are held constant, consuming
source-closed dependency hints improves exact imported-target Recall@12 without
required loss or material precision, latency, privacy, or regression harm.

The acceptance system has one authoritative future contract:
`tests/fixtures/p15_v7_minimal_online_causal/attempt-contract.json`. No run-local
document may add, delete, or reinterpret a gate. The contract binds the
candidate, online identities, prompt and schema, corpus, queries, gold, causal
factor, outcome gates, release gates, and governance state.

Outcome proves whether P15 is useful. Release and governance decide whether a
useful result is safe and auditable enough to ship. A release or governance
failure must not be reported as an efficacy failure.

## 2. Single authoritative contract and freeze transition

After DRAFT approval, the contract has exactly two pre-execution states:

1. `pre_corpus_frozen`: bind attempt ID, baseline and candidate product
   projections, the only treatment factor, SiliconFlow planner and embedding
   identities, Qwen model, prompt and response-schema hashes, TopK, corpus
   generation and selection rules, the complete fixed sampling schedule/order
   rule and cardinalities, all outcome/release/governance gates, and the held-out
   public seal digest. Fresh repository identities and cases remain empty.
2. `sealed_before_candidate`: append only the independently selected repository
   identities, commits, inventories, twelve fresh cases, their two control-only
   online sample artifacts, shared pre-treatment-state hashes, and exact corpus
   denominators. It also binds the fully expanded, finite execution schedule for
   every concrete case, sample, arm, and replay. Every `pre_corpus_frozen` field
   must remain byte-identical.

The transition is one reviewed append-only binding. Candidate execution is
forbidden before `sealed_before_candidate`. After that state, any change to the
candidate, model, prompt, schema, corpus, query, gold, gate, or denominator
requires a new attempt ID. A separate run-local gate file is not authoritative.
The expanded schedule is complete before any treatment result is read. No
result-dependent replay, retry, extra sample, replacement slot, or schedule
append is allowed.

The contract has three clearly separated result sections:

- `outcome`: fresh efficacy and conditional held-out decisions;
- `release`: performance, privacy, regression, focused/full tests, and CI;
- `governance`: freeze identity, no tuning, evidence completeness, and final
  disposition.

## 3. Frozen candidate and online identity

The control and treatment use the same candidate product projection, model,
prompt, schema, index, embeddings, query, base candidate roster, budgets, and
TopK. The only factor is:

- control: do not consume dependency hints;
- treatment: consume dependency hints with the frozen source-closed local rule.

The planner is the frozen SiliconFlow-hosted Qwen identity. The embedding path is
the frozen SiliconFlow identity. Local endpoints and Ollama are forbidden.
Temperature, seed, request limits, prompt hash, schema hash, model name, provider
domain, and endpoint are attempt identity, not evidence that the online model is
deterministic.

## 4. Fresh corpus

Fresh efficacy uses two independently ordered Python repositories. Before any
online request, each repository contributes exactly the first six structurally
eligible cases in the frozen independent order:

- structural indices 1–2 are the two guard cases, used only for loss, rank-1,
  noise, determinism, privacy, and latency safety; and
- structural indices 3–6 are the four frozen efficacy candidates.

The primary efficacy denominator is therefore eight gold target files. Guard
targets and anchors do not increase that denominator and cannot provide the
three required efficacy gains.

### 4.1 Independent structural gold

An independent stdlib-AST procedure derives each case from a direct local
`from module import name [as alias]` statement. The target module/file must
resolve uniquely, and the imported name must identify one unique top-level
`FunctionDef`, `AsyncFunctionDef`, or `ClassDef` owned by that file. The direct
exact import edge, source signal/chunk/file, and target signal/chunk/file form the
closed causal witness.

The query is source-only. It may contain mechanically derived source symbol,
source module, and source behavior terms. It must not contain the imported
target name or alias, target module, target path, target signal, gold label, or a
term derived from any of those values.

### 4.2 Candidate-blind selection

Before any control call, freeze exactly structural indices 1–6 per repository:
indices 1–2 are guard and indices 3–6 are efficacy. Do not scan index 7 or later,
make an online qualification request, replace a case, or replace a repository.

Selection may use only:

- repository structure and the independent direct-import gold derivation;
- the frozen independent structural order; and
- the exact fixed indices 1–6.

Selection must not read or derive:

- treatment or candidate output;
- imported-target hint values;
- exact source-identity hint matches;
- planner status as a reason to delete a case;
- a candidate admissible-target roster or candidate rank;
- whether gold is among the first one, two, or any number of candidate winners;
- private candidate helpers or a reimplementation of the promotion decision.

All twelve frozen cases then complete both online samples and all local replays.
If an efficacy candidate's gold target appears in control Top12 in either
sample, classify the corpus as `INCONCLUSIVE_CORPUS` only after the complete
24-sample and 96-local-replay matrix is recorded. Do not stop early, scan a
later case, or replace the case or repository.

Planner fallback remains in the frozen cohort and denominator and may not cause
replacement. Cases are distinct by query, source path, and target path.

Anchors and the source path are protected context. They are recorded for safety
but do not enter target Recall or the eight-item primary denominator.

## 5. Online sampling and same-plan causal replay

Every one of the twelve fresh queries has exactly two predeclared real online
samples. For each sample:

1. Call the frozen SiliconFlow Qwen planner exactly once.
2. Validate the response with the frozen strict JSON parser. If validation
   fails, freeze the product fallback plan; do not delete or replace the case.
3. Build and hash one shared pre-treatment state: validated/fallback plan,
   embedding/index identity, query embedding result, base candidate roster,
   base scores/order, caps, and request accounting.
4. Replay control and treatment locally from that exact shared state. No second
   planner or embedding request is allowed for the treatment.
5. Replay each local arm exactly twice. Within one sample and arm, normalized
   Top12, target rank, rank-1 path, causal witness projection, and score/order
   projection must be exact.

The frozen fresh execution order is repository rank, then frozen case ordinal,
then sample 1 followed by sample 2. In sample 1, local replay order is control 1,
control 2, treatment 1, treatment 2. In sample 2, it is treatment 1, treatment 2,
control 1, control 2. The complete fresh matrix is therefore exactly 24 planner
samples and 96 local arm replays. The held-out sealed payload binds the same
two-sample, two-arm, exactly-two-replay order for every hidden case.

Different online samples are allowed to produce different planner JSON, base
rosters, scores, and Top12. Cross-sample exact equality is not a gate. Causal
credit is computed inside each same-plan sample and then combined across the two
samples.

All twelve cases and both samples must finish before an outcome decision. There
is no “repeat only after first-round success” or early stop after efficacy
success/failure. A provider outage that prevents the frozen sample matrix from
completing is `blocked`, not a reason to switch model, endpoint, case, or repo.

## 6. Outcome gates

### 6.1 Fresh efficacy

A stable causal new target is an efficacy-case gold target that, in both online
samples, is absent from control Top12 and present in treatment Top12, with exact
same-sample local replay and a closed source-relation-target-chunk witness.

Fresh efficacy passes only when all of the following hold:

1. at least three stable causal new targets across three distinct efficacy
   cases;
2. at least one stable causal new target in each fresh repository;
3. zero required target loss across all twelve cases and both samples;
4. zero treatment rank-1 changes across all twelve cases and both samples;
5. every credited gain has the closed exact witness;
6. at least 90% of the 24 planner calls return a valid plan, which means at
   least 22 valid plans; invalid plans remain in the denominator via fallback;
7. aggregate Precision@12 decreases by no more than `0.02`; and
8. at most one treatment-only irrelevant `(case, sample, path)` is introduced.

The candidate-blind relevance set contains the anchor, source, gold target, and
all independently derived closed direct-import target paths for the source. It
does not use candidate output.

Target Recall@12 for control and treatment and its delta are always reported.
Recall has no separate numeric pass floor: the integer three-gain gate and the
frozen eight-target denominator define the minimum effect without denominator
games.

### 6.2 Held-out

One independently sealed Python repository contains at least four
candidate-blind target-missing efficacy cases built by the same source-only,
independent-AST rules. Its public contract and sealed payload digest are bound in
`pre_corpus_frozen`; queries, gold, and outcomes remain unopened until fresh
efficacy passes.

After fresh passes under the same single approval receipt, use two real online
samples per held-out query and the same-plan local replay protocol. Held-out passes with at least two stable causal
new targets across two cases and zero required target loss. No model, prompt,
schema, local rule, query, case, threshold, or denominator may change after
opening.

## 7. Release gates

Release gates are evaluated separately from outcome:

- the treatment makes zero additional planner or embedding requests;
- shared-plan local treatment median latency regresses by at most 10%, or its
  absolute median increase is at most 5 ms;
- end-to-end online latency is reported but is not a hard gate;
- planner payload contains only the query and frozen numeric limits, never repo
  identity, path, source/snippet, target/gold, or candidate information;
- all remote calls use the frozen SiliconFlow domains and identities;
- localhost and Ollama request counts are zero;
- no credential, authorization header, source body, absolute local path, or raw
  exception text appears in tracked evidence or logs;
- TopK, graph/retrieval caps, and work budgets do not increase; and
- focused tests, the full suite, and CI pass as ship gates.

Planner and embedding latency, provider errors, fallback counts, and end-to-end
latency remain visible in the report. They cannot be hidden by case deletion.

## 8. Governance and removed gates

The final disposition is:

- `accept_outcome`: fresh and held-out outcome gates pass;
- `ship`: `accept_outcome` plus every release and governance gate passes;
- `reject_outcome`: the complete planned sample matrix runs and an outcome gate
  fails;
- `blocked`: the frozen online service or sealed input is unavailable without a
  substitution; or
- `release_reject`: outcome passes but a release/governance gate fails.

P15-v7 explicitly removes from efficacy and corpus eligibility:

- v1/v2 oracle recovery and recursive legacy-evidence revalidation;
- v3 evidence-security harness construction and `live40`-style process
  choreography;
- v4/v5 target-derived queries and candidate-conditioned selection;
- v4 “repeat only if first pass” stopping;
- v5/v6 deletion of planner fallback cases;
- v5/v6 cross-sample exact Top12 equality;
- v6 exact source-hint match as an eligibility gate;
- v6 gold-among-first-two-admissible-targets selection;
- exact score-part/reason strings, promotion formulas, and private helper behavior
  as evidence of product effectiveness.

Those implementation identities may have focused unit tests, but they do not
select the corpus or provide efficacy credit. This design authorizes no new
security harness.

## 9. Current stop point

The only authorized work in this revision is this design and its companion plan.
Stop after their static review and SHA recording. Code, tests, the authoritative
JSON contract, corpus access, online requests, fresh execution, and held-out
opening await a separate explicit authorization.
