"""Milestone 1, final wiring: capabilities, the mode command, and handle_run."""

import re
import sys

F = "Selftest_pmu/runner_pmu_main.c"
s = open(F).read()


def sub1(old, new, what):
    global s
    n = s.count(old)
    if n != 1:
        sys.exit("FAIL %s: expected 1 match, found %d" % (what, n))
    s = s.replace(old, new)


# One name for one concept: COMPLETION_WAIT_MODE_BUSY_POLL already exists.
sub1('''/* The frozen u85 driver waits for completion by polling, so the CPU is active
 * throughout NPU execution. Results from a future WFI variant describe a
 * different machine state and must not be pooled with these. */
#define COMPLETION_WAIT_BUSY_POLL 1U''',
     '''/* The frozen u85 driver waits for completion by polling, so the CPU is active
 * throughout NPU execution. Results from a future WFI variant describe a
 * different machine state and must not be pooled with these. The constant is
 * COMPLETION_WAIT_MODE_BUSY_POLL, declared with the capability enums below --
 * one name for one concept. */''',
     "drop duplicate busy-poll constant")

# --------------------------------------------------------------- capabilities
sub1('''    /* --- PMU: UNSUPPORTED THIS MILESTONE. All zero, by instruction. ---
     * The PMU registers are not even read: PMU work is a later milestone and
     * a zero here must be read as "not implemented", never as "measured 0". */
    put32(&c, 0U); /* PMU_TYPE                 -- unsupported */
    put32(&c, 0U); /* PMU_EVENT_COUNTER_COUNT  -- unsupported */
    put32(&c, 0U); /* PMU_COUNTER_WIDTH        -- unsupported */
    put32(&c, 0U); /* pmu_supported            -- 0 */''',
     '''    /* --- NPU PMU discovery -------------------------------------------
     * This DOES touch the PMU, deliberately. The OFF contract is scoped to the
     * RUN PATH, not to the whole session: capabilities is a discovery call
     * made outside any measurement window, and pmu_probe_performed says so.
     * Reporting a hardware count needs the hardware to be asked. */
    pmu_probe();
    put32(&c, pmu_reg_read(NPU_REG_PMCR));  /* raw PMCR */
    put32(&c, pmu_hw_event_counters);       /* PMCR.num_event_cnt */
    put32(&c, NPU_PMU_EVENT_COUNTER_WIDTH); /* 32, event counters */
    put32(&c, pmu_present);''',
     "capabilities PMU slots")

sub1('''    put32(&c, RUNNER_TX_DRAIN_US);
    put32(&c, RUNNER_TX_RESIDUAL_CHARS);''',
     '''    put32(&c, RUNNER_TX_DRAIN_US);
    put32(&c, RUNNER_TX_RESIDUAL_CHARS);
    /* --- appended: the three capacities kept apart, plus what OFF/END_ONLY
     * this build actually supports. ABI capacity is a wire-format property;
     * hardware capacity is what the device reports; effective is the only one
     * that bounds a configuration request. */
    put32(&c, pmu_probe_performed);
    put32(&c, RUNNER_MAX_NPU_EVENT_COUNTERS);   /* abi_event_slot_count */
    put32(&c, pmu_effective_event_slots());
    put32(&c, NPU_PMU_CYCLE_COUNTER_WIDTH);     /* 48, not 64 */
    put32(&c, (1U << INSTRUMENTATION_OFF) | (1U << INSTRUMENTATION_END_ONLY));''',
     "capabilities appended fields")

sub1("#define CAP_FIELD_COUNT 29U",
     "/* 29 + 5 appended for the PMU candidate. */\n#define CAP_FIELD_COUNT 34U",
     "capability field count")

# ------------------------------------------------------------- mode command
anchor = "static void handle_reset_runner("
handler = '''/* ------------------------------------------------------------------------ */
/* CMD_SET_INSTRUMENTATION_MODE                                              */
/*                                                                           */
/* Payload, 44 bytes:                                                        */
/*   u32 mode              OFF | END_ONLY (PER_LAYER -> ERR_UNSUPPORTED)     */
/*   u32 event_set_id                                                        */
/*   u32 event_count                                                         */
/*   u32 event_codes[8]                                                      */
/*                                                                           */
/* The reply reports REQUESTED and APPLIED separately. A request that cannot  */
/* be honoured is refused, never silently clamped -- a host that asked for    */
/* more counters than exist must find out, not receive a quiet subset.        */
static void handle_set_instrumentation_mode(uint32_t sequence,
                                            const uint8_t *payload,
                                            uint32_t payload_length)
{
    uint8_t  resp[16];
    uint32_t mode, set_id, count, effective;
    uint32_t codes[RUNNER_MAX_NPU_EVENT_COUNTERS];
    unsigned i;

    if (payload_length != (12U + (RUNNER_MAX_NPU_EVENT_COUNTERS * 4U))) {
        send_nack(CMD_SET_INSTRUMENTATION_MODE, sequence, ERR_LENGTH);
        return;
    }

    mode   = rd_u32(&payload[0]);
    set_id = rd_u32(&payload[4]);
    count  = rd_u32(&payload[8]);
    for (i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        codes[i] = rd_u32(&payload[12U + (i * 4U)]);
    }

    if (mode != INSTRUMENTATION_OFF && mode != INSTRUMENTATION_END_ONLY) {
        /* PER_LAYER and anything else: well-formed but not implemented here.
         * Distinct from BAD_COMMAND so the host can tell them apart. */
        send_nack(CMD_SET_INSTRUMENTATION_MODE, sequence, ERR_UNSUPPORTED);
        return;
    }

    effective = pmu_effective_event_slots();
    if (count > RUNNER_MAX_NPU_EVENT_COUNTERS || count > effective) {
        send_nack(CMD_SET_INSTRUMENTATION_MODE, sequence, ERR_RANGE);
        return;
    }
    /* Milestone 1 is cycle-only. Event programming lands in milestone 2, and
     * accepting a count now would report event slots that were never armed. */
    if (count != 0U) {
        send_nack(CMD_SET_INSTRUMENTATION_MODE, sequence, ERR_UNSUPPORTED);
        return;
    }

    instr_cfg.mode         = mode;
    instr_cfg.event_set_id = set_id;
    instr_cfg.event_count  = count;
    for (i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
        /* Unused slots are zeroed, but a zero is never how a slot is judged --
         * event_valid_mask is the authority, because code 0 can be real. */
        instr_cfg.event_codes[i] = (i < count) ? codes[i] : 0U;
    }
    instr_cfg.configuration_sequence++;

    wr_u32(&resp[0], mode);                            /* requested */
    wr_u32(&resp[4], instr_cfg.mode);                  /* applied   */
    wr_u32(&resp[8], instr_cfg.event_count);
    wr_u32(&resp[12], instr_cfg.configuration_sequence);
    send_ack(CMD_SET_INSTRUMENTATION_MODE, sequence, resp, sizeof(resp));
}

'''
sub1(anchor, handler + anchor, "mode handler")

sub1('''    case CMD_RESET_RUNNER:
        handle_reset_runner(sequence);
        break;''',
     '''    case CMD_RESET_RUNNER:
        handle_reset_runner(sequence);
        break;
    case CMD_SET_INSTRUMENTATION_MODE:
        handle_set_instrumentation_mode(sequence, payload, payload_length);
        break;''',
     "dispatch")

# ------------------------------------------------------------------ handle_run
sub1('''    r.ts_open = read_timestamp();

    run_rc = run_fixed_inference();

    r.ts_close = read_timestamp();''',
     '''    r.ts_open = read_timestamp();

    /* A COPY of the configuration, taken before anything runs. Changing the
     * mode after this point must not rewrite this run's record. */
    {
        const instrumentation_config_t cfg = instr_cfg;
        const uint32_t pmu_r0 = pmu_mmio_read_count;
        const uint32_t pmu_w0 = pmu_mmio_write_count;
        uint32_t ts_prog_start, ts_prog_end;
        uint32_t cycle_stable = 0U, cycle_retries = 0U, ovf = 0U;
        uint64_t cycles = 0U;
        unsigned i;

        r.record_schema_version          = 1U;
        r.instrumentation_mode_requested = cfg.mode;
        r.event_set_id                   = cfg.event_set_id;
        r.configuration_sequence         = cfg.configuration_sequence;
        r.abi_event_slot_count           = RUNNER_MAX_NPU_EVENT_COUNTERS;
        r.expected_hw_event_counter_count = NPU_PMU_EVENT_COUNTERS_MAX;
        r.requested_event_count          = cfg.event_count;
        r.completion_wait_mode           = COMPLETION_WAIT_MODE_BUSY_POLL;
        for (i = 0; i < RUNNER_MAX_NPU_EVENT_COUNTERS; i++) {
            r.event_codes[i] = cfg.event_codes[i];
        }

        ts_prog_start = read_timestamp();
        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
            npu_pmu_disable();
            npu_pmu_reset_counters();
            r.npu_pmu_present          = pmu_present;
            r.pmu_probe_performed      = pmu_probe_performed;
            r.hw_event_counter_count   = pmu_hw_event_counters;
            r.effective_event_slot_count = pmu_effective_event_slots();
        }
        ts_prog_end = read_timestamp();
        r.t_pmu_programming = ts_prog_end - ts_prog_start;

        __DSB();
        __ISB();

        r.t_pmu_enable = read_timestamp();
        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
            npu_pmu_enable();
        }

        r.t_inference_call_enter = read_timestamp();
        run_rc = run_fixed_inference();
        r.t_inference_call_return = read_timestamp();

        /* Disable FIRST, snapshot second: stopping the counter as close to the
         * return as possible bounds what the window can contain, and a stopped
         * counter cannot tear. The stable read stays regardless, because the
         * ordering of the disable against the MMIO read is not guaranteed. */
        if (cfg.mode == INSTRUMENTATION_END_ONLY) {
            npu_pmu_disable();
            r.t_pmu_disable = read_timestamp();
            cycles = npu_pmu_read_cycles(&cycle_stable, &cycle_retries);
            ovf    = npu_pmu_overflow_status();

            r.npu_pmu_window_cycles_lo = (uint32_t)(cycles & 0xFFFFFFFFU);
            r.npu_pmu_window_cycles_hi = (uint32_t)(cycles >> 32);
            r.npu_pmu_cycle_overflow   = (ovf & NPU_PMU_CYCLE_OVF_BIT) ? 1U : 0U;
            r.npu_pmu_cycle_read_retry_count = cycle_retries;
            /* A torn read or a wrapped counter is NOT a measurement. 48 bits
             * cannot be un-wrapped from endpoints alone, so the overflow flag
             * is the authority and invalidates the sample. */
            r.npu_pmu_cycle_valid =
                (cycle_stable && !r.npu_pmu_cycle_overflow) ? 1U : 0U;
            r.pmu_sample_valid    = 1U;
            /* Milestone 1 arms no event counters: every slot stays invalid. */
            r.event_valid_mask    = 0U;
            r.event_overflow_mask = 0U;
            r.applied_event_count = 0U;
        } else {
            r.t_pmu_disable = read_timestamp();
        }

        r.instrumentation_mode_applied = cfg.mode;
        r.cpu_call_window_cycles =
            r.t_inference_call_return - r.t_inference_call_enter;
        r.cpu_return_to_pmu_disable_cycles =
            r.t_pmu_disable - r.t_inference_call_return;
        /* The runtime half of the OFF contract: in OFF this must be 0/0. */
        r.pmu_mmio_read_count_delta  = pmu_mmio_read_count - pmu_r0;
        r.pmu_mmio_write_count_delta = pmu_mmio_write_count - pmu_w0;
    }

    r.ts_close = read_timestamp();''',
     "handle_run wiring")

open(F, "w").write(s)
print("patched %s" % F)
