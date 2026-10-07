# V15 deployment — 2026-08-23

Authorized: deploy the anchored candidate, verify read-back, issue the
production cell context, close Task 11. **The 3×10 campaign remains
unauthorized and was not started.**

Preflight evidence was frozen as `v15-board-preflight-passed` before the first
write.

## Deployed

The already-qualified candidate, taken out of the container with `docker cp`.
Nothing was rebuilt or regenerated.

| | source | manifest | destination |
| --- | --- | --- | --- |
| `APP.BIN` | `4967fa39…` | `4967fa39…` | `4967fa39…` |
| `VECTORS.BIN` | `6864a22b…` | `6864a22b…` | `6864a22b…` |
| `DDR.BIN` | `81d37a21…` | `81d37a21…` | `81d37a21…` |

**source == manifest == destination.**

The read-back is not a re-read of the files just written — that can be answered
from the page cache, which confirms the write *call* rather than the write. The
card was synced, unmounted, and remounted read-only, so the hashes came off the
device.

Then unmounted (`findmnt` 0 rows), `USB_OFF` issued and confirmed, `/dev/sdb*`
absent.

## Fresh boot on the deployed image

| | |
| --- | --- |
| DDR self-test | PASSED |
| CPUWAIT | cleared |
| PING | 3/3 answered from IDLE |
| protocol counters | all seven zero |

`REBOOT` re-enables the debug USB, so `USB_OFF` was reissued afterwards and
`/dev/sdb*` confirmed absent again. Four UART ports free, root-inclusive.

## Production VerifiedCellContext

Issued through the real gate, against a destination read-back taken from the
device — not a synthetic or hand-built context.

```
comparison_mode      Q_S5_EQUIVALENT
candidate_identity   0c3ac91a…
analysis ELF         49d22540…
manifest             4be8f268…
boot_id              v15-deploy-20260823-boot1
```

## A partial write, and what was done about it

The first deployment script died from a bug of mine (an argument-name collision
in a logging helper) immediately after writing `APP.BIN`. The card was then
`APP` = V15, `VECTORS` = original, `DDR` = the same bytes either way: a partial
deployment.

It was closed to a safe state first — sync, unmount, `findmnt` 0, `USB_OFF` —
before anything else. Then the bug was fixed and all three images were written
again, with the read-back above. **The board was never booted or measured in the
partial state.**

The same bug had already occurred once earlier in the session, in a collection
script where it cost nothing. Here it happened mid-write. Fixing the pattern the
first time would have prevented it.

## A defect found and fixed

`verify_evidence_chain` returned the manifest's own self-hash under
`manifest_sha256`, while `open_verified_cell` returned the external digest under
the same name. A preflight and a context would have reported different values
for one document and looked like they had seen different manifests.

Unified on the external digest, with the self-hash kept as a separate key. Two
regression tests, mutation RED.

```
manifest_sha256     4be8f268…   (both entries agree)
manifest_self_hash  42bb2310…   (separate key)
```

## Not performed

No campaign. `CAMPAIGN_SAMPLES = 0`. No V15 measurement run had been executed at
the time of writing; Task 11 closure needs one frame and that question was put
to the manager rather than decided here.
