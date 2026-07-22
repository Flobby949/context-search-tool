# P6 benchmark contracts

This directory defines the closed, versioned acceptance contracts for P6
freshness, performance, and large-repository evidence.

The JSON Schemas in `schemas/` reject unknown fields. Committed reports must
contain both the implementation commit and the exact
`src/context_search_tool` tree identity; a commit string alone is not
sufficient. Baseline reports may describe unsupported pre-P6 operations, while
final performance reports must include the complete 100-step churn result.

Benchmark inputs are deterministic generated repositories described by
`tests/fixtures/p6_performance/workload_manifest.json`. Generated source and
all working directories remain under ignored `.quality/` roots and are never
committed. Exact candidate fixtures contain only generated identifiers, finite
scores, score parts, and result digests.

Published artifacts must not contain source bodies, vector values, secrets,
environment dumps or values, credential-bearing URLs, process command lines,
absolute temporary paths, or unapproved real query text. Repository paths are
relative POSIX paths and may appear only in bounded allowlisted samples.

The supported measurement states are `cli_process_cold`,
`mcp_resident_warm`, and informational
`filesystem_cold_diagnostic`. Duration uses milliseconds, storage and RSS use
bytes, throughput uses MiB/s, and ratios are unitless. Raw same-case samples
must never be mixed across operation, query case, workload, identity, or cache
state.

The functional matrix installs the exact universal resolution in `uv.lock` and
binds the raw lock-file SHA-256 into each matrix summary. An operation/state
combination that the measured production tree does not implement is recorded as
`unsupported`; it must not be represented by a synthetic zero-duration sample.
The workload manifest's closed benchmark registry is authoritative for each
operation/case/state sample count, so `run` has no default-case or one-sample
escape hatch. Tier case reports may be assembled into a per-tier performance
report and those reports may be assembled again without losing case identity.
The CLI requires every registry measurement for a tier—including explicit
`unsupported` measurements—before it will assemble, validate, or publish that
tier. A combined performance report must contain all four publication tiers:
`smoke`, `large`, `scale-5k`, and `scale-10k`. Repository fingerprints are
checked against the manifest before calibration or measurement begins.

Each `run` invocation either measures one exact registered
operation/case/state tuple, using `--operation`, `--case-id`, `--samples`, and
`--measurement-state`, or measures a closed tier batch selected with
`--operations`. The allowed batches are `all-smoke` for `smoke`, `all-large`
for `large`, `all-scale` for `scale-5k` and `scale-10k`, and
`capacity-informational` for `stress`. Baseline is the default mode; final
capture must explicitly select `--mode final`. The frozen 100-step churn uses
the separate `churn` subcommand. Baseline capture enumerates the tuples from
`benchmark_registry.cases`, assembles one complete performance report per tier,
then assembles the four publication tiers. The environment summary uses stable
host facts shared by all case reports, the maximum observed background CPU and
swap growth, median calibration values, and maximum paired calibration drift.
Mixed stable host facts fail closed.

`run` writes immutable per-sample checkpoints beside its requested output by
default, using the `<output>.checkpoints/` directory. A completed sample is
atomically persisted only after its warmup and measured operation both finish.
If a process is interrupted, repeat the exact command with `--resume`; the
runner verifies the implementation tree, harness, workload and query fixtures,
repository state, host identity, case, cache state, mode, and sample count
before skipping completed samples. Checkpoints are ignored local evidence and
are never published. Worker heartbeats and sample-phase progress are emitted to
stderr so a long full-build measurement is distinguishable from a stalled
process.

TDD evidence uses one canonical `tdd-task-N.json` record per task plus a
uniquely suffixed record for every later measured amendment. Quality assembly
validates every supplied checkpoint independently and publishes ordered,
privacy-safe checkpoint summaries; it never merges distinct pre-change commits
into one synthetic TDD identity.

ANN and service/watch records are decisions only. They cannot encode
implementation authorization: ANN is either retained or requires a separately
reviewed prototype amendment, and service/watch is deferred or eligible for a
separate design.
