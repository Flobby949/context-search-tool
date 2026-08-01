# P15-v3 Closed Exact-Provenance Bonus Design

Status: frozen review candidate; capture is not authorized.

## 1. Purpose and boundary

P15-v2 proved that exact imported-symbol edges expand resolved structure but do not, by themselves, change selected results. P15-v3 therefore evaluates one ranking-only factor: a closed, binary exact-provenance bonus. The policy was frozen and independently approved before either fresh efficacy repository was identified; this revision binds the later independent public seals without changing that policy.

This phase creates only an independent v3 specification, plan, fixture, acceptance validator, and tests. It does not modify `src/`, call an online or local model, open Click, add an oracle, or create the v3 run directory.

## 2. Sole policy: B

Policy B is the only permitted policy. Policy A is permanently forbidden and will not be run, recorded as an alternative arm, or revived after seeing efficacy results.

For each case:

1. Complete the existing stable base ranking with all pre-existing behavior unchanged.
2. An exact-provenance atom has the closed tuple `(relation_id, source_signal_id, source_file_path, source_chunk_id, target_signal_id, target_file_path, target_chunk_id, relation_kind, resolution, producer, resolution_basis, ordered_edge_position)`. It is emitted only by a direct `python_ast` `imports` relation whose resolution and basis are both `resolved_exact` / `exact_python_imported_symbol`. No hop, ancestor, descendant, adjacent graph relation, selected-result witness, name similarity, or later context relation may emit or propagate an atom.
3. Candidate acquisition, same-chunk merge, and context-overlap merge each expose their input atoms. Merge computes a deterministic set union, deduplicated by the complete tuple above and sorted lexicographically by that tuple. Merge can preserve an atom emitted by a direct input, but cannot synthesize one. A merged candidate is eligible only when at least one atom also passes the exact candidate identity join: `candidate.file_path == atom.target_file_path` and one member of `candidate.origin_chunk_ids == atom.target_chunk_id`. Counts or Boolean claims are never eligibility evidence.
4. Freeze the complete existing pre-bonus total order after identifier-definition-owner scoring, ceiling clamp, project/frontend cohort rerank, and before context expansion. Its sort projection is exactly `(-round(rerank_score, 3), evidence_priority, 0 if was_ceiling_clamped else 1, -pre_ceiling_rerank_score if clamped else 0.0, role_priority, -rerank_score, -combined_score, file_path, start_line, chunk_id)`. The runtime roster must contain every ranked candidate and all fields needed to recompute this projection.
5. Among all candidates whose eligibility is recomputed from their closed atoms, choose exactly one winner: the eligible candidate with the minimum complete pre-bonus projection. The full roster proves that no better eligible candidate was omitted. Input iteration order cannot change the winner.
6. Add `0.04` to that winner's `rerank_score`, add the score part named exactly `exact_imported_symbol` with value `0.04`, and add the reason named exactly `exact imported symbol dependency`. These strings are closed and cannot drift.
7. Recompute the same complete total-order projection with the winner's post-bonus `rerank_score` and rerank the full roster. No tie-break, owner, ceiling, cohort, combined score, or other candidate field changes.
8. Multiple exact edges never accumulate. Eligibility is a Boolean/max operation, not a sum: the maximum contribution per case is `0.04`.
9. Apply the bonus after the complete existing base rank and before context expansion/final selection. The bonus cannot affect candidate acquisition, graph expansion, merging, or the computation of its own eligibility.

The single-factor ablation is exactly `0.00 -> 0.04`. No other arm or adaptive tuning is permitted after fresh repository identities are disclosed.

### Task0 two-phase ablation with an external control-seal gate

Runtime evidence is produced in two ablation phases separated by an independent review gate. Treatment is forbidden until the control phase is externally sealed and that seal's exact byte digest is bound by a reviewed manifest/harness revision.

Phase A is raw control with `policy_contribution = 0.00`. For each query, four write-new captures run in separate processes: repeat 1/canonical order, repeat 1/reverse order, repeat 2/canonical order, and repeat 2/reverse order. Every raw capture persists the complete cohort-rerank output candidate roster, the actual ordered direct-edge inventory, all candidate/same-chunk/context-overlap merge inputs, deterministic provenance unions, and every field of the existing stable order. The validator reconstructs the runtime projection from each raw capture; all four projections must be exactly equal. Their PIDs and invocation IDs must all be distinct.

Only an independent freeze step, with its own PID and invocation ID distinct from every raw-control capture, may then create a canonical, read-only (`0444`), write-new control-freeze marker. The marker binds all four raw-control paths, byte/canonical digests, the common stable-projection digest, the exact repeat/order matrix, capture and freezer producer/process identities, schema, privacy disposition, and zero policy contribution. After the four raw controls and marker are written, capture must stop.

The intermediate Task0R gate is performed by an independent reviewer with a new PID and invocation ID. From the fixed `task0a-control` path, the reviewer reads the actual bytes and `lstat` metadata of the exact five-file inventory: four raw controls plus the marker. Every file must be canonical JSON, mode `0444`, a regular non-symlink with link count one, and write-new. The reviewer validates the complete roster/edge/merge inventory, all four byte and canonical SHA-256 digests, all four stable-projection digests, the marker byte/canonical digest, exact inventory, and capture/freezer/reviewer PID isolation. It then writes a canonical, mode-`0444`, write-new external control-seal disposition at the fixed sibling path. The seal itself must be a regular non-symlink with link count one.

Phase B is treatment with `policy_contribution = 0.04`. It remains unauthorized until a new manifest/harness revision binds the exact external-seal byte SHA-256. A treatment record may contain only that external-seal reference/digest, one exact seal-listed raw-control reference/digests, an independent treatment process identity, and the treatment output. It may not contain a candidate roster, edge inventory, merge input, provenance union, eligibility claim, or pre-bonus order. The treatment validator accepts only a run-root path plus the manifest-bound seal digest: it rereads the seal, marker, selected raw-control snapshot, and treatment bytes from their fixed paths and never accepts those evidence payloads from memory. From the seal-anchored raw bytes it reconstructs edge positions, tuple unions, eligibility, pre-bonus winner, and complete pre-bonus order before verifying the unique binary bonus and post-bonus order.

Raw-control, freezer, external-reviewer, and treatment PIDs/invocation IDs must be pairwise disjoint. Producer, process identity, schema, privacy status, canonical serialization, file inventory, stat requirements, and write-new paths are closed. Rewriting all four controls, the marker, treatment, and every internal digest still fails because the rewritten external seal cannot match the separately manifest-bound seal digest. Missing seals, wrong file modes, symlinks/hardlinks, or extra control files fail before treatment output is considered.

## 3. Frozen non-changes

P15-v3 must not change any of the following:

- `top_k = 12`;
- relation-slot count or slot ownership;
- total context budget, graph budget, candidate budget, or token budget;
- relation or expansion caps;
- definition-owner behavior or weight;
- existing imports relation weight `0.85`;
- existing graph decay `0.8`;
- existing relation score part `graph_imports_match` or reason `static module dependency`;
- outgoing-only traversal, seed rules, hop rules, merge semantics, context expansion, or final-selection rules.

Frozen cap constants are:

- maximum graph seed signals: 512;
- maximum resolved graph hops: 4;
- maximum edges per signal per direction: 64;
- maximum relation-expanded candidates: 1000;
- maximum Python imports per file: 256.

The new score part is additional visibility for one already-ranked candidate; it does not consume, replace, reserve, or reassign a relation slot.

## 4. Closed structural and cap invariants

For every repository capture, the validator consumes a closed structural projection with exactly these top-level keys: `selected_files`, `non_relation_fields`, `relation_buckets`, `module_projection_sha256`, and `non_python_projection_sha256`. `non_relation_fields` has exactly `active_chunks` and `signals_by_producer`. The baseline contract freezes the complete producer and relation-bucket key sets; neither arm may omit or add a key. Selected files, every non-relation value, every producer bucket, the module projection, the non-Python projection, and every relation bucket other than `imports:resolved_exact` must be directly equal. The one allowed equality is:

`oracle imports:resolved_exact = baseline imports:resolved_exact + oracle causal_relation_count`.

The frozen v2 examples are:

| Repository | Baseline | Exact arm | Causal count |
| --- | ---: | ---: | ---: |
| Starlette | 119 | 254 | 135 |
| Requests | 73 | 200 | 127 |
| RedInk | 35 | 73 | 38 |
| Daily | 696 | 1889 | 1193 |

Every cap constant must be identical between arms. For each source signal:

`exact observed_max_outgoing <= baseline observed_max_outgoing + maximum_exact_relations_per_source`.

The frozen observed bounds are Starlette `24 -> 38` with maximum exact degree 16, Requests `28 -> 51` with 27, RedInk `10 -> 13` with 5, and Daily `44 -> 108` with 64.

### Saturation visibility

Daily reaches the full allowed delta: `108 - 44 = 64`. The proof is not a generated numeric range. It is bound to the 64 real direct exact relations for source signal `s5:00b95fd8ae31d8ca420a00beebc3255abac75483ee5719bca61ff79ee2a762e2` (`src/core/pipeline.py`) in immutable v2 oracle capture SHA-256 `f60c6f4a2065a1aab65913dbd6aed3662eb9ef22146e9e48aebd9fd1eef64a01`. Their complete identity projection is frozen by SHA-256 `c59f96bd2158a16037df322920a2263096413e0bd7a19a4eac9660351942c7f6`; the manifest enumerates each actual relation identity at its deterministic position 1 through 64. The validator reconstructs every complete identity from v2 evidence and compares the frozen digest and order. The position-65 negative relocates the real position-64 edge identity to position 65 and must fail solely on the cap. Any identity substitution, missing/duplicate position, position above 64, or cap increase fails closed.

### Runtime visibility

The raw-control acceptance evidence for every case must expose, before context expansion:

- the full candidate roster, not only eligible or selected candidates;
- each merge input route (`candidate`, `same_chunk`, `context_overlap`) and every complete provenance atom contributed by that route;
- a hash-bound, deterministically ordered direct-edge inventory from the actual graph-expansion input, with unique relation identities and unique `(source_signal_id, ordered_edge_position)` pairs; every merge atom must exactly belong to this inventory and every position must be at most 64;
- the deterministic complete-tuple union and dedupe result derived from those inventory-bound atoms;
- each candidate's `file_path`, complete `origin_chunk_ids`, and the exact tuple join used to derive eligibility;
- all numeric/string fields needed to recompute the frozen pre-bonus total-order projection and positions;
- the one winner derived from the full roster, thereby proving no higher-ranked eligible candidate is omitted;
- exactly one winner when the eligible set is nonempty and no winner when it is empty;
- the exact `exact_imported_symbol` score part and `exact imported symbol dependency` reason on the winner only;
- `0.04` as the maximum case contribution regardless of the number of exact provenance items;
- the full post-bonus roster reranked with the same total order; and
- the fixed stage boundary `after_owner_ceiling_and_cohort_before_context_expansion_and_final_selection`.

The validator derives union, dedupe, eligibility, winner, and the pre-bonus order from raw control. It derives the treatment post-bonus order from the same raw control plus the fixed contribution. Self-reported treatment Booleans, counts, rosters, or edges are forbidden, not merely ignored. These fields make the causal factor observable without relying on selected-result witness metadata after final selection.

## 5. Evidence classes

Starlette, Requests, RedInk, and Daily are permanently protected legacy characterization repositories in v3. They may prove structural, cap, regression, and runtime-visibility invariants, but provide zero fresh efficacy credit.

The complete P15-v2 terminal rejection is immutable input. The v3 harness must verify the v2 reject index at `.quality/p15-runs/p15-v2-attempt-001/reject-index.json`, SHA-256 `cde8f5baf1aa8b6e96f04fdc24f221b450824563cb5721a59cf40872c3a69dd5`, and recursively verify every identity, disposition, capture, comparison, terminal artifact, and exact inventory bound by that index.

Fresh efficacy uses recovery-v2 seals for the unchanged independently selected HTTPX commit `b5addb64f0161ff6bfe94c124ef76f6a1fba5254` and poetry-core commit `5de24118d23a05a23af5d9eb1d8bd98850d09205`. HTTPX binds public contract `89e4a783fbb612c8d2863bae21594976d3467ff87726971c7b178fc0c3e23a59`, ciphertext metadata `5eff61dd8c4159e15b041f510abbca11c275f035bb2021279df53bdfeb8e4268`, and plaintext identity metadata `c107d7a744154d93c54041dd9b026d31ed2fe6cc7d53775ccffafa931737ac75`. Poetry-core binds public contract `8428aaf2c2b952e579e75ec388031000cb9594b66784ed811e88e24d25903ec7`, ciphertext metadata `40a011a5272fb748ae116a087f1d4c9998c9ebc18b69bc837b45ab136cb04ccf`, and plaintext identity metadata `385c15af37c226ac869b3dcdc84f5b4d6750fb1bad83aabab7ea362fdde0f8cf`.

The recovery-v2 roster SHA-256 is `303a08e0e1c18f845abea8e44bb2a074bc58bb6aef30b4448c9111638a039266`; its seal-hash index SHA-256 is `0b7f4e3c69857b9fbb0e3e96b67ba1e5d9b84adc84dbff04fe7fb65ec96905de`. The only active seal directory is `.quality/p15-v3-recovery-seal-v2`, with exactly five public JSON files and two ciphertexts. Each public contract fixes source URL, commit/tree, SPDX license and digest, include/exclude inventory, content digest, PBKDF2-HMAC-SHA256 parameters, and strict plaintext serialization `canonical_json_sort_keys_compact_utf8_no_trailing_newline`. Each repository has four cases, denominator 12, and four baseline-missing unique-exact-signal-eligible items; combined headroom remains eight cases, denominator 24, and eight eligible missing items. The encrypted payloads are opaque: the validator checks only `lstat` metadata (`0600`, expected lengths 15952 and 18784, regular non-symlink, link count one), never their bytes. Recovery-v2 plaintext/release files remain absent, and release and capture remain unauthorized.

The prior fresh seal directory, manifest/harness rebind disposition, release-byte supplemental disposition, and ciphertext-probe incident disposition are archived and revoked as active release/capture authority. They remain preserved for history but cannot appear in any active fresh field. The recovery-v2 roster and seal-hash index bind their archived identities and statuses; no old artifact can authorize or supply recovery-v2 release or capture.

## 6. Click boundary

Click is conditional carry-forward only under recovery-v2 disposition SHA-256 `9ace5e51975f21fc626556ab99673a7ec66650896e44a37c9618e8dc956be009`. The disposition carries forward immutable predecessor public metadata without modifying, hashing, or opening any Click file during recovery. The validator reads only the new public disposition, requires zero Click reads/decryption/capture, and checks only absence of the plaintext and open-record paths. No Click open, capture, decryption, or efficacy claim is authorized.

## 7. Acceptance and authorization

The v3 skeleton is acceptable for independent review when:

- the design, plan, manifest, harness, and tests are independently named and hash-bound;
- the sole policy and all non-change invariants are closed and mutation-tested;
- the v2 rejection and every bound v2 artifact revalidate;
- structure, cap, Daily saturation, and runtime-visibility formula tests pass;
- both fresh public seals, source inventories, KDF metadata, and combined headroom validate while release and capture remain disabled;
- Click carry-forward validates while the open gate remains sealed and conditional;
- the v3 run root is absent and `src/context_search_tool` has no P15 change.

This revision is `awaiting_recovery_v2_rebind_review`. It does not release either recovery-v2 payload or authorize capture. Any later release or capture eligibility requires independent approval of this exact recovery-v2 manifest/harness rebind and a separate explicit authorization.
