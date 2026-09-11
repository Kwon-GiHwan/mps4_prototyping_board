F = "runner_proto.py"
s = open(F).read()

assert s.count("CMD_RESET_RUNNER = 0x50") == 1
s = s.replace("CMD_RESET_RUNNER = 0x50",
              "CMD_RESET_RUNNER = 0x50\nCMD_SET_INSTRUMENTATION_MODE = 0x05")

assert "ERR_UNSUPPORTED" not in s
s = s.replace("ERR_RESULT_NOT_VALID = 0x000B",
              "ERR_RESULT_NOT_VALID = 0x000B\nERR_UNSUPPORTED = 0x000C")

anchor = "    def reset_runner(self) -> None:"
method = '''    def set_instrumentation_mode(self, mode: int, event_codes=(),
                                 event_set_id: int = 0):
        """Set mode and event configuration. Returns (requested, applied,
        applied_count, configuration_sequence).

        The firmware refuses rather than clamps, so a NACK here means the
        request was rejected outright and the previous configuration stands.
        """
        codes = list(event_codes)
        if len(codes) > NPU_PMU_ABI_EVENT_SLOTS:
            raise ProtocolError("at most %d event codes" % NPU_PMU_ABI_EVENT_SLOTS)
        payload = struct.pack("<III", mode, event_set_id, len(codes))
        payload += b"".join(struct.pack("<I", c) for c in codes)
        payload += b"\\x00" * (4 * (NPU_PMU_ABI_EVENT_SLOTS - len(codes)))
        f = self.request(CMD_SET_INSTRUMENTATION_MODE, payload)
        return struct.unpack("<IIII", f.payload[:16])

'''
assert s.count(anchor) == 1
s = s.replace(anchor, method + anchor)
open(F, "w").write(s)
print("set_instrumentation_mode added")
