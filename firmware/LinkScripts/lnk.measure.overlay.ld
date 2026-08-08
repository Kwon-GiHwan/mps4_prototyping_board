/******************************************************************************
 * lnk.measure.overlay.ld -- RUNNER_V1_MEASURE address-contract symbols.
 *
 * Applied ON TOP of the FROZEN LinkScripts/lnk.ld.S:
 *
 *     -T $(BUILD)/lnk.ld  -T LinkScripts/lnk.measure.overlay.ld
 *
 * The shared lnk.ld.S is NOT edited by this deliverable. That file feeds two
 * frozen builds (build_gcc, build_runner) and every byte of their output is
 * a gate, so the MEASURE-only symbols live here instead.
 *
 * SYMBOL ASSIGNMENTS ONLY. This file must never contain an output section, a
 * MEMORY block, or anything else that could place or relocate content. If a
 * future edit here changes a single byte of the frozen builds, the change is
 * wrong by construction.
 *
 * Note on what is NOT here:
 *   __sec_noinit_start / __sec_noinit_end already exist in the frozen script
 *   (added for runner_v1), so the GET_RESULT permitted-range bounds need no
 *   new definition at all.
 *
 *   There is deliberately NO tight pair around .bss.sec_output_data. Bounding
 *   that single input section requires symbol assignments INSIDE the
 *   .sec_noinit output-section body, which only the shared lnk.ld.S can
 *   express -- ADDR()/SIZEOF() operate on whole output sections and cannot
 *   see an input-section boundary from an overlay. The C object is no help
 *   either: test3_out_data_0 (Tests/u85_test/test3/test3_include.h:125) is
 *   declared `static`, so it has no external linkage. Providing it would
 *   therefore require editing either the frozen linker script or a frozen
 *   test header, and neither is done here.
 ******************************************************************************/

/* Model staging window in DDR: 0x90120000 .. 0x91120000 == 16 MiB.
 * These are fixed constants and could equally come from --defsym; they are
 * kept here so that the whole address contract reads from one file. */
__runner_staging_start__ = 0x90120000;
__runner_staging_end__   = 0x91120000;

/* Result region == the whole .sec_noinit output section, which is exactly the
 * range GET_RESULT validates against. ADDR()/SIZEOF() resolve correctly from
 * an overlay because .sec_noinit is an OUTPUT section defined by the base
 * script (verified: see MEASURE_PROVENANCE.txt). */
__runner_result_start__ = ADDR(.sec_noinit);
__runner_result_end__   = ADDR(.sec_noinit) + SIZEOF(.sec_noinit);
