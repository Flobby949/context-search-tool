# P6 cloud full-build acceptance decision

- Acceptance status: **SUCCESS**
- Scope: `smoke / full_build / default / cli_process_cold / baseline`
- Decision authority: user
- Decision basis: explicit user acceptance with runner-environment and merge-gate waivers
- Decision date: 2026-07-20
- Source run: [GitHub Actions run 29714191723](https://github.com/Flobby949/context-search-tool/actions/runs/29714191723)
- Implementation commit: `f4cb316fdd8f89bbfba4d470070f8920620d12be`
- Production tree: `f3d89faaaa1c1be8a557817917da6dc9baa16664`
- Harness SHA-256: `1434eba5c91bf37b9ca3b6ee061c4931df6cb45a689cb6b07e36644a800c319d`
- Workload SHA-256: `8426f41615c2dbdbc9fc59a0d5c3dbb3ec6f496cb6c63c0b08fbf437f414f644`

## Evidence

All five independent cloud sample jobs completed successfully. Each produced
one schema-valid immutable checkpoint for the same implementation, production
tree, harness, workload, repository state, operation, case, measurement state,
mode, and requested five-sample population.

The measured sample median was `5,232,384.497352001 ms`, the nearest-rank p95
and maximum were `5,472,948.833833002 ms`, and the population coefficient of
variation was `0.023202256422477866`.

Checkpoint SHA-256 values:

- `sample-001`: `8c56b77b5a3de4c343df6b4a3bc90d771b55a46ca4d99a892e4b074cc5d412af`
- `sample-002`: `a975f0731eb8871a3df64e947c0d5667e636d853c6c37e51872e3cacd1c9f167`
- `sample-003`: `2e8c82a58ee7d7cb4cd958fa09326175c7fbd40ce47a609c4c1f115a9153d3f9`
- `sample-004`: `6b2b2e4b7c7089dd8b2b224f84ea8b0a85b6fcf0523b695a8f2f99ee226180a4`
- `sample-005`: `3e33d0e7a0113d94f4d36070462032437e3b930049f500e41df7912c73b34219`

## Waivers

The workflow merge job rejected mixed stable-environment identities. By
explicit user decision, the following gates are waived for this scoped cloud
acceptance: `mixed_stable_environment`, `background_cpu`, `host_cpu`,
`host_memory`, `disk_class`, `power_state`, and `governor_state`.

This decision records acceptance as successful without deleting, rewriting, or
relabeling the underlying workflow logs or checkpoint evidence.
