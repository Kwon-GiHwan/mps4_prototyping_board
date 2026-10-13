# Amendment 1 to the Tier B contract (2026-09-23, before any data)

`RULE_CAPABILITY` is observed through the protocol the host actually has:
`RunnerLink` exposes no capabilities read, so the host cannot inspect the
advertised mode mask. The image lacking mode 2 is observed instead as the
first `SET_INSTRUMENTATION_MODE(mode=2)` returning NACK `ERR_UNSUPPORTED`.
That NACK trips `RULE_CAPABILITY`; a NACK with any other code, or an ACK whose
`applied != 2`, trips `RULE_MODE_NACK`. Nothing else changes.
