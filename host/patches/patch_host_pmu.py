F = "runner_proto.py"
s = open(F).read()

def sub1(old, new, what):
    global s
    assert s.count(old) == 1, "%s: %d matches" % (what, s.count(old))
    s = s.replace(old, new)

sub1("RME_MAX_WORDS = MAX_PAYLOAD // 4",
     '''RME_MAX_WORDS = MAX_PAYLOAD // 4

# The PMU candidate appends 51 fields. Both images declare abi_version 1, so
# the field count -- never the version -- decides what can be decoded. A
# MEASURE_SEQ payload (55 words) stays fully parseable; its PMU block is absent
# and is reported as None, never as zeros.
RME_PMU_FIELDS_V1 = 51
RME_PMU_TOTAL_WORDS = RME_HEADER_WORDS_V1 + RME_KNOWN_FIELDS_V1 + RME_PMU_FIELDS_V1

INSTRUMENTATION_OFF = 0
INSTRUMENTATION_END_ONLY = 1
COMPLETION_WAIT_MODE_BUSY_POLL = 1
NPU_PMU_CYCLE_WIDTH_BITS = 48
NPU_PMU_ABI_EVENT_SLOTS = 8

_PMU_SCALARS_A = [
    "record_schema_version", "instrumentation_mode_requested",
    "instrumentation_mode_applied", "event_set_id", "configuration_sequence",
    "npu_pmu_present", "pmu_probe_performed", "hw_event_counter_count",
    "expected_hw_event_counter_count", "abi_event_slot_count",
    "effective_event_slot_count", "requested_event_count",
    "applied_event_count", "event_valid_mask", "event_overflow_mask",
]
_PMU_SCALARS_B = [
    "npu_pmu_window_cycles_lo", "npu_pmu_window_cycles_hi",
    "npu_pmu_cycle_valid", "npu_pmu_cycle_overflow",
    "npu_pmu_cycle_read_retry_count", "pmu_sample_valid",
    "completion_wait_mode", "t_pmu_enable", "t_inference_call_enter",
    "t_inference_call_return", "t_pmu_disable", "t_pmu_programming",
    "cpu_call_window_cycles", "cpu_return_to_pmu_disable_cycles",
    "t_result_processing", "pmu_mmio_read_count_total",
    "pmu_mmio_write_count_total", "pmu_mmio_read_count_delta",
    "pmu_mmio_write_count_delta", "pmcr_at_disable",
]


def decode_pmu_block(words):
    """Decode the 51 appended PMU fields.

    Two rules that must not be relaxed:
      - an event slot is judged ONLY by event_valid_mask. Code 0 can be a real
        event, so an invalid slot yields None, not 0.
      - npu_pmu_window_cycles is None unless cycle_valid is set. The name stays
        "window": the snapshot is taken after the inference call returns, not
        in the completion ISR, so it is not NPU execution time.
    """
    if len(words) < RME_PMU_FIELDS_V1:
        raise ProtocolError("PMU block shorter than %d fields" % RME_PMU_FIELDS_V1)
    out, i = {}, 0
    for name in _PMU_SCALARS_A:
        out[name] = words[i]
        i += 1
    codes = list(words[i:i + NPU_PMU_ABI_EVENT_SLOTS]); i += NPU_PMU_ABI_EVENT_SLOTS
    values = list(words[i:i + NPU_PMU_ABI_EVENT_SLOTS]); i += NPU_PMU_ABI_EVENT_SLOTS
    for name in _PMU_SCALARS_B:
        out[name] = words[i]
        i += 1

    mask = out["event_valid_mask"]
    ovf = out["event_overflow_mask"]
    out["event_codes"] = [codes[n] if (mask >> n) & 1 else None
                          for n in range(NPU_PMU_ABI_EVENT_SLOTS)]
    out["event_values"] = [values[n] if (mask >> n) & 1 else None
                           for n in range(NPU_PMU_ABI_EVENT_SLOTS)]
    out["event_overflow"] = [bool((ovf >> n) & 1) if (mask >> n) & 1 else None
                             for n in range(NPU_PMU_ABI_EVENT_SLOTS)]

    raw = out["npu_pmu_window_cycles_lo"] | ((out["npu_pmu_window_cycles_hi"] & 0xFFFF) << 32)
    raw &= (1 << NPU_PMU_CYCLE_WIDTH_BITS) - 1
    out["npu_pmu_window_cycles_raw"] = raw
    out["npu_pmu_window_cycles"] = raw if out["npu_pmu_cycle_valid"] else None
    return out''',
     "PMU constants and decoder")

sub1("""        fields=body[:RME_KNOWN_FIELDS_V1],
        trailing_words=len(body) - RME_KNOWN_FIELDS_V1,
    )""",
     """        fields=body[:RME_KNOWN_FIELDS_V1],
        trailing_words=len(body) - RME_KNOWN_FIELDS_V1,
    )
    # Absent, not zero: an image without the PMU block must be distinguishable
    # from one that measured zeros.
    m.pmu = (decode_pmu_block(body[RME_KNOWN_FIELDS_V1:])
             if total_words >= RME_PMU_TOTAL_WORDS else None)
    return m""",
     "attach PMU block")

# the function previously ended with `return Measurement(...)`; bind it first
sub1("    return Measurement(\n", "    m = Measurement(\n", "bind measurement")

open(F, "w").write(s)
print("patched runner_proto.py")
