# Amendment 2 to the Tier B contract (2026-09-23, after boot 3 refused itself, before any run)

"The host verifies PING counters are all zero before the first set" is made
exact: the **seven error counters** (`rx_overrun`, `bad_magic`, `bad_version`,
`bad_crc`, `length_error`, `sequence_error`, `parser_resync`) must be zero.
`rx_bytes` / `tx_bytes` are traffic counters and include the PING request
frame itself (20 bytes), so they can never be zero at the time of the reply
and are not judged. This is the same set the 2026-08-09 qualification record
calls "에러 카운터 7종".

Boot 3 (host-boot-index 3) was refused by the literal reading (`rx_bytes=20`,
all seven error counters 0) and is archived as a refusal with zero runs. It
is not reused; the campaign re-runs on a fresh boot (index 4).
