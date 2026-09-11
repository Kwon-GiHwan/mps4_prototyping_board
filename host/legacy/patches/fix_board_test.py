F = "test_pmu_board.py"
s = open(F).read()

old = '''def do_run(link, mode):
    """RESET (which forces OFF) -> set mode -> prime -> RUN. Returns pmu dict."""
    link.reset_runner()
    link.set_instrumentation_mode(mode)
    prime(link)
    # prime() resets again, so the mode must be re-stated after it.
    link.set_instrumentation_mode(mode)
    link.load_input(b"")
    rc = link.run()'''
new = '''def do_run(link, mode):
    """RESET -> set mode -> load -> RUN.

    Order is forced by two contracts working together: RESET_RUNNER returns the
    mode to OFF (deliberately, so nothing is inherited), and the mode may only
    be set in IDLE. So the mode is set immediately after the reset and the load
    sequence must NOT reset again -- which is why this does not call prime().
    """
    link.reset_runner()
    link.set_instrumentation_mode(mode)
    blob = b"\\x00" * 64
    link.load_model_begin(len(blob), zlib.crc32(blob) & 0xFFFFFFFF)
    link.load_model_chunk(0, blob)
    link.load_model_end()
    link.load_input(b"")
    rc = link.run()'''
assert s.count(old) == 1
s = s.replace(old, new)

old2 = '''link.set_instrumentation_mode(INSTRUMENTATION_END_ONLY)
link.reset_runner()
prime(link)
rc, mr, crcr = do_run(link, INSTRUMENTATION_OFF)'''
new2 = '''link.reset_runner()
link.set_instrumentation_mode(INSTRUMENTATION_END_ONLY)
link.reset_runner()          # must wipe the END_ONLY setting
rc, mr, crcr = do_run(link, INSTRUMENTATION_OFF)'''
assert s.count(old2) == 1
s = s.replace(old2, new2)

open(F, "w").write(s)
print("fixed: mode is set right after reset, no second reset")
