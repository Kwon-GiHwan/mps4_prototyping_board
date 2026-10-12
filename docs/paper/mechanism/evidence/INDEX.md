# Mechanism-study raw evidence — by stage and experiment date

Experiment dates are from server file metadata (mtime,
`gihwan:/home/gihwan/mps4/U85_MECH_*`); git does not preserve mtimes, so
the windows are recorded here. Within each stage: `uart-logs/` raw FVP UART
captures, `run-vectors/` parsed per-run vectors and build identities,
`reports/` campaign reports and analyzer outputs, `vela-debug/` debug-db
XML and verbose-schedule captures, `build-logs/` cmake configure/build
logs, `tools/` the exact scripts run, `manifests/` SHA-256 manifests of the
original archive, `misc/` uncategorized remainders (fvp stdout logs,
launches.json), `binaries.tar.gz` AXF/BIN/tflite/map/generated sources
(mtimes preserved inside the tar).

| stage | UTC window (2026-09-02) | origin archive |
| --- | --- | --- |
| 20260902-p0c0-commandstream-feasibility | 00:19–01:26 | U85_MECH_P0C0_20260902T003028Z |
| 20260902-p0c-profiling-qualification | 01:50–01:57 | U85_MECH_P0C_20260902T015728Z |
| 20260902-p0d-formal-clean | 02:03–02:46 | U85_MECH_P0D_20260902T024627Z |
| 20260902-p0d2-profiled-irqhistory | 02:03–05:16 | U85_MECH_P0D2_20260902T051659Z |
| 20260902-p1a-memory-robustness | 06:17–06:39 | U85_MECH_P1A_20260902T063919Z |
| 20260916-p0e2-two-workload | 2026-09-15 20:46–21:30 | acquired in place; no server archive |

The server archives remain the frozen originals; each stage's
`manifests/EVIDENCE.sha256` verifies file identity against them.

P0-E2 extends the same layout with two workloads, Wav2Letter and MobileNetV2,
over the three existing bindings.

Note the date in its directory name. Every other row above is named for its
UTC date and the two agree. P0-E2's directory is named for the campaign date
in the contract, 2026-09-16 local (UTC+9), while the acquisition itself ran
2026-09-15 20:46–21:30 UTC. The window column stays UTC, like the rest of the
table.

It was acquired directly into `20260916-p0e2/` rather than from a server
archive, so its `manifests/EVIDENCE.sha256` is the origin record rather than a
check against one. `reports/` additionally carries the pre- and post-state
digests of the patched files, the gate report and the mutation report.
