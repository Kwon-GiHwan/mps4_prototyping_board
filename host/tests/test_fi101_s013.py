import sys, unittest, pathlib
REPO = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "host" / "analysis"))
import fi101_s013 as S


def run(active=100, infer=120, window=1000, cpu=120, mac=50, beats=(1, 2, 3, 4), valid=True, fired=1):
    ev = {35: active, 48: mac, 130: beats[0], 135: beats[1], 386: beats[2], 391: beats[3]}
    return dict(ev=ev, ovf=set(), valid=valid, window=window, infer=infer, infer_cpu=cpu, sys=None, host_s=None,
                start_fired=fired)


def runs(*rs):
    return {(1, i + 3): r for i, r in enumerate(rs)}


class Stage0(unittest.TestCase):
    def test_green(self):
        self.assertEqual(S.stage0(runs(run(), run(active=101)), runs(run(active=99), run(active=102))),
                         {"S0-1": "PASS", "S0-2": "PASS", "S0-3": "PASS", "S0-4": "PASS", "S0-5": "PASS"})

    def test_each_check_can_fail(self):
        ref = runs(run(), run())
        for key, bad in {"S0-1": run(fired=2), "S0-2": run(infer=90), "S0-3": run(cpu=130),
                         "S0-4": run(mac=51), "S0-5": run(active=103, infer=130, cpu=130)}.items():
            self.assertEqual(S.stage0(runs(run(), bad), ref)[key], "FAIL", key)
        self.assertEqual(S.stage0(runs(run(), run(valid=False)), ref)["S0-1"], "FAIL")
        self.assertEqual(S.stage0(runs(run(beats=(1, 2, 3, 5)), run()), ref)["S0-4"], "FAIL")
        self.assertEqual(S.stage0(runs(run(active=120), run(active=120)), ref)["S0-4"], "FAIL")   # outside ref range
        self.assertEqual(S.stage0(runs(run()), None)["S0-4"], "UNPROVEN")
        self.assertEqual(S.stage0(runs(run(infer=1001, cpu=1001)), ref)["S0-2"], "FAIL")          # infer > window

    def test_verdicts(self):
        self.assertEqual(S.verdict([1, 2], False), "COUNTED_NONZERO")
        self.assertEqual(S.verdict([0, 0], False), "COUNTED_ZERO")
        self.assertEqual(S.verdict([0, 2], False), "INCONSISTENT")
        self.assertEqual(S.verdict([1, 2], True), "OVERFLOW")
        self.assertEqual(S.verdict([], False), "NOT_OBSERVED")

    def test_ratio_uses_the_same_run(self):
        r = runs(run(active=100, mac=50), run(active=200, mac=50))
        self.assertEqual(S.ratio(r, 48, 35), (0.5 + 0.25) / 2)


def brun(active=100, mac=50, beats=None, valid=True, set_id=2):
    ev = {35: active, 48: mac}
    ev.update(beats or {e: 10 for e in S.CHAN_EVENTS})
    return dict(ev=ev, ovf=set(), valid=valid, window=1000, infer=120, infer_cpu=120, sys=None, host_s=None)


class Channels(unittest.TestCase):
    def base(self):
        return {(2, 3): brun(), (2, 4): brun(active=101)}

    def test_works(self):
        ch = {"rd_weights": {(1, 3): brun(beats={e: 4 for e in S.CHAN_EVENTS})},
              "wr_ofm": {(1, 3): brun(beats={e: 10 for e in S.CHAN_EVENTS})}}
        self.assertEqual(S.channel_check(self.base(), ch)[0], "CHANNEL_FILTER_WORKS")

    def test_each_condition_can_fail(self):
        above = {e: 11 for e in S.CHAN_EVENTS}
        for ch in ({"x": {(1, 3): brun(beats=above)}},                                   # above unfiltered
                   {"x": {(1, 3): brun()}},                                              # nothing below
                   {"x": {(1, 3): brun(active=120, beats={e: 4 for e in S.CHAN_EVENTS})}},   # execution changed
                   {"x": {(1, 3): brun(valid=False, beats={e: 4 for e in S.CHAN_EVENTS})}},  # invalid run
                   {"lo": {(1, 3): brun(beats={e: 4 for e in S.CHAN_EVENTS})},              # one below, one above
                    "hi": {(1, 3): brun(beats=above)}},
                   {}):
            self.assertEqual(S.channel_check(self.base(), ch)[0], "CHANNEL_FILTER_UNPROVEN", ch)


if __name__ == "__main__":
    unittest.main()
