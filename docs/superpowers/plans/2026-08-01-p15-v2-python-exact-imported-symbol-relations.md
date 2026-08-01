# P15-v2 Python Exact Imported-Symbol Relations Implementation Plan

Date: 2026-08-01

Status: Review candidate. Starlette and Requests replacement seals and released
development-payload digests are hash-bound. Blocked on independent plan review
and final harness closure. Not authorized for capture or implementation.

Normative design:
`docs/superpowers/specs/2026-08-01-p15-v2-python-exact-imported-symbol-relations-design.md`

## Goal

Run a new, product-free oracle for the unchanged exact imported-symbol
hypothesis against two independently selected replacement efficacy repositories.
Only after that oracle passes may the same narrow four-file product change be
implemented and evaluated.

P15-v2 is not a continuation of a successful v1 attempt. P15-v1 attempt-003 is
a frozen Task-0 reject and none of its captures counts as v2 evidence.

## Frozen Boundaries

The following do not change from the reviewed P15-v1 contract:

- R1 `python_declaration` union selector and exact same-file/unit lookup;
- one retained module relation plus one exact declaration relation;
- actual allowed targets `type` and `function` from `python_ast` Python signals;
- relation kind/weight/decay/score key/reason/direction;
- current ranking, selection, evidence merge, query, and planner behavior;
- every graph/retrieval cap and budget;
- numeric R2 thresholds, causal credit rule, TopK `12`;
- SiliconFlow provider/model/dimensions/endpoint/pacing with planner disabled;
- Click held-out contract, ciphertext, denominator, and opening protocol;
- allowed product files.

Daily and RedInk fixtures remain unchanged but are protected characterization
only. They never contribute to v2 efficacy denominators or gain counts. Two
independent replacement repositories supply all v2 development efficacy.

## Task 0A: Archive the v1 terminal state

1. Verify `.quality/p15-runs/p15-v1-attempt-003/reject-index.json` is new and
   immutable.
2. Recompute every indexed capture/comparison hash.
3. Verify the comparison disposition is `reject`, no hash-proceed marker or
   online capture exists, Click is unopened, and the product tree is clean.
4. Never overwrite or relabel a v1 artifact.

Verification: exact indexed hashes match and v1 remains terminal.

## Task 0B: Independent replacement seals and review

An independent reviewer, not the implementation executor, must select two
public Python efficacy-development repositories. Before any v2 capture, the
reviewer freezes for each repository:

1. URL, exact commit/tree, license and provenance;
2. deterministic source inclusion and immutable inventory/content hashes;
3. exact queries, required/contextual roles, protected winners, TopK `12`, and
   closed-world noise labels;
4. enough required items and cases to measure the unchanged R2 arithmetic;
5. a public contract plus sealed-payload digest and timestamp;
6. evidence that no v2 product diff or capture preceded sealing.

The independent review must also decide explicitly that the unopened Click v2
seal may be carried forward unchanged. If not, stop and seal a new held-out
before continuing; never open Click merely to make that decision.

Verification: two replacement contracts and the plan-review disposition are
`approved`; all skeleton placeholders can be replaced without changing a
threshold, credit rule, or product policy.

The reviewer selected and bound:

- Starlette at `5174d4c8358a6f06aa8056bafd14c2272dab8dd1`, public contract
  SHA-256 `d230a78f86ab1225305e454b83a674e391faec5c4c024ee89c050fb6eefc35d8`,
  released development payload SHA-256
  `309388945b12fb9becc15e2d037d85bfc7f09299f469dde5d8d5a8642fcd6182`;
- Requests at `414f0513c33883adf6f2b46901d4f0b38a455851`, public contract
  SHA-256 `19a116a434debaba3dde6dfbeb3848d5a298477f79280be06d0c982c1a2ede51`,
  released development payload SHA-256
  `cfa75bd1cf2cba1b4456fbf590c02fe85fd418d0e1e1c4032e880c569fd7f1ee`;
- roster contract SHA-256
  `27ad5f2b6abb2f9d11c202877bb56f3e76cbcaaa5d58e1059b79fdffb1446823`.
- seal-hashes manifest SHA-256
  `17e069d90f66899d0dab7b433b91b40620a55bcc92df881d1e038aa55cc78b1f`.

Both released hashes match the corresponding sealed plaintext digest. This
satisfies the seal/release hash gate only; independent design/plan and Click
carry-forward review remain blocking.

## Task 0C: Close the v2 manifest and harness

Use only new artifacts:

- `tests/fixtures/p15_v2_python_import_symbols/input_manifest.json`;
- `tests/p15_v2_python_import_symbol_acceptance.py`;
- `tests/test_p15_v2_python_import_symbol_acceptance.py`;
- `.quality/p15-runs/p15-v2-attempt-001/`.

Until Task 0B passes, the skeleton harness must validate only the pending
identity and reject every capture command before indexing or provider setup.
After review:

1. replace both pending replacement slots with reviewed contracts and hashes;
2. record final design, plan, manifest, harness, gold, source, and seal hashes;
3. bind every evidence slot to `p15-v2-attempt-001`, phase, corpus, profile,
   variant, repeat, input order, implementation identity, and product tree;
4. require write-new evidence and reject any existing run-root artifact;
5. prove v2 has no imported v1 capture or marker;
6. keep Click sealed and all key material outside project evidence;
7. add negative tests for wrong roles, hashes, denominators, thresholds,
   absolute paths, source bodies, witness fields, repeat drift, and local-model
   paths.

The final review disposition must independently bind the exact design and plan
paths and SHA-256 values. A manifest value that merely agrees with a
simultaneously edited document is not sufficient. The harness hard-codes the
v1 reject-index SHA-256, P8 protected-gold path/SHA-256, reviewer roster and
seal-hashes SHA-256 values, and recomputes the complete protected case/source
projections.

Verification: harness tests pass and the preflight reports zero v2 captures.

## Task 0D: Product-free hash oracle

Only after Tasks 0B and 0C pass, create fresh baseline indexes for:

- replacement efficacy repository A;
- replacement efficacy repository B;
- Daily protected characterization;
- RedInk protected characterization.

The independent oracle parses `ImportFrom`, starts from the one P8 exact module
relation, resolves exactly one allowed declaration in the exact file/unit,
inserts one test-only already-resolved edge using the target's actual kind, and
reruns the unchanged retrieval pipeline.

Run baseline and oracle in separate processes for repeats `1` and `2`, each in
canonical and reversed input order, with hash embeddings and planner off. Run
performance-sensitive captures sequentially. Compare normalized projections
byte-for-byte after masking only predeclared timing/implementation fields.

Apply efficacy arithmetic only to the two replacements. Apply all loss, noise,
winner, module, non-Python, membership, integrity, request, retrieval, and work
caps to all four development/characterization repositories.

If any hash gate fails, write a terminal reject and stop. Do not run online,
open Click, change product code, or revise gold/threshold/credit/policy.

## Task 0E: Confirmatory online safety

Only after a hash proceed marker exists, run two separate-process baseline and
oracle captures with:

```text
openai-compatible / Pro/BAAI/bge-m3 / 1024
https://api.siliconflow.cn/v1
planner disabled
240000 tokens/minute
80000 tokens/request
2 second minimum interval
p14-bounded-greedy-v1 batching
```

Guard Ollama/local paths fail closed and count actual online requests,
retrieval calls, fallbacks, errors, and skips. Online stable projections must
match; online cannot supply missing hash efficacy.

**Task-0 proceed condition:** replacement seals and plan review approved;
manifest/harness closed; v2 evidence starts empty; hash and online gates pass;
Daily/RedInk protections pass; Click remains sealed; product diff remains empty.

## Tasks 1-4: Conditional product implementation

These tasks remain unauthorized until Task 0 proceeds.

1. RED/GREEN imported-name and alias AST facts in `python_graph.py`.
2. RED/GREEN R1 union resolution and strict integrity in
   `graph_resolution.py` and `sqlite_store.py`.
3. RED/GREEN independent cap, module-before-exact bounded reads, atomic store,
   and no-orphan invariants in `sqlite_store.py`.
4. RED/GREEN canonical lifecycle handling in `graph_lifecycle.py`: producer
   version `1` to `2` at schema `5`; missing/0/1 stale once with
   `producer_contract_changed`; authoritative atomic ready-v2 rebuild; second
   refresh parses zero files; malformed/negative/non-canonical/future versions
   fail closed; unchanged vector rows and embedding IDs are reused; and
   change/revert plus delete/restore converge.

Every product edit must trace to the unchanged v2 design. No ranking,
selection, relation-policy, expansion, query, planner, schema, weight, or
budget edit is permitted.

## Tasks 5-7: Conditional candidate acceptance

After focused/full regression suites pass:

1. freeze the candidate product tree and harness identity;
2. only then follow the independently reviewed held-out opening protocol;
3. run candidate hash captures on replacements, characterizations, and Click;
4. require production to recover every oracle-credited replacement gain;
5. require at least two new Click required items across two cases;
6. run the confirmatory SiliconFlow matrix with planner off;
7. enforce performance, determinism, lifecycle, privacy, raw-CI, and full-suite
   gates;
8. obtain independent Standards and Spec reviews with no blocking finding.

Final acceptance requires every frozen automatic gate. A failure is a reject,
not permission to tune or waive.

## Present Stop Condition

At this review-candidate stage, Tasks 0D onward are blocked. The next authorized
state change is the independent design/plan and Click carry-forward review
disposition, followed by final manifest/harness closure. No capture, online
request, held-out opening, or `src/context_search_tool` edit may occur before
those gates pass.
