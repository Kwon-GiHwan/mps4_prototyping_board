#!/usr/bin/env python3
"""Mutation/negative tests for pd_analyzer: every rejection rule must be
provably able to fire, and the mapping/boolean derivations must be exact."""
import copy
import unittest

import pd_analyzer as A


def op(idx, typ="Conv2D", ofm="1, 4, 4, 8", kernel="size=1,1 stride=1,1",
       slices=1, ublock="[2, 2, 8]", block="OFM[1] IFM[1]", stripes="OFM[x] ",
       cascade="0", weight_buf="0", vela=100, tidx=0):
    return {"idx": idx, "type": typ, "ofm": ofm, "kernel": kernel,
            "slices": slices, "ublock": ublock, "block": block,
            "stripes": stripes, "cascade": cascade, "weight_buf": weight_buf,
            "vela_cycles": vela, "time_index": tidx}


def prof(records, tail_total):
    lines = ["PLPROF_BEGIN,%d" % len(records)]
    for i, (c, e) in enumerate(records):
        lines.append("PLPROF,%d,%d,%s" % (i, c, ",".join(map(str, e))))
    lines.append("PLPROF_END")
    return {"plprof": "\n".join(lines), "pl_count": len(records),
            "total": tail_total}


class TestMapping(unittest.TestCase):
    def test_tail_maps_to_last_launch(self):
        ops = [op(0), op(1)]
        p = prof([(50, [40, 1, 2, 3, 4])], 70)   # 1 record + tail
        out = A.op_cycles(ops, p)
        self.assertEqual(out[0]["ccnt"], 50)
        self.assertEqual(out[1]["ccnt"], 70)
        self.assertTrue(out[1]["tail_in_op"])

    def test_slice_aggregation(self):
        ops = [op(0, slices=2), op(1)]
        p = prof([(10, [1] * 5), (20, [2] * 5)], 30)
        out = A.op_cycles(ops, p)
        self.assertEqual(out[0]["ccnt"], 30)      # two slices summed
        self.assertEqual(out[0]["evt"], [3, 3, 3, 3, 3])
        self.assertEqual(out[1]["ccnt"], 30)

    def test_full_records_no_tail(self):
        ops = [op(0), op(1)]
        p = prof([(10, [1] * 5), (20, [2] * 5)], 999)
        out = A.op_cycles(ops, p)
        self.assertEqual(out[1]["ccnt"], 20)
        self.assertFalse(out[1]["tail_in_op"])

    def test_record_count_mismatch_rejects(self):
        ops = [op(0), op(1), op(2)]
        p = prof([(10, [0] * 5)], 99)             # 1 record, 3 launches
        with self.assertRaises(A.Reject):
            A.op_cycles(ops, p)

    def test_plcount_field_mismatch_rejects(self):
        ops = [op(0)]
        p = prof([(10, [0] * 5)], 99)
        p["pl_count"] = 2
        with self.assertRaises(A.Reject):
            A.op_cycles(ops, p)


class TestIdentity(unittest.TestCase):
    def test_identity_ignores_ublock(self):
        a, b = op(0), op(0, ublock="[1, 1, 1]")
        self.assertEqual(A.identity(a), A.identity(b))

    def test_identity_distinguishes_kernel(self):
        a, b = op(0), op(0, kernel="size=3,3 stride=1,1")
        self.assertNotEqual(A.identity(a), A.identity(b))


class TestScheduleParse(unittest.TestCase):
    SAMPLE = """Schedule: 'g'
\t0: Operation Conv2D  - OFM 1, 49, 10, 140
\t\tKernel: size=4,10 stride=1,1, dilation=1,1 padding=[t:4]
\t\tTime index = 0
\t\tOperator Config = OFM Block=[1, 24, 10, 16], IFM Block=[1, 32, 14, 16], OFM UBlock=[2, 2, 16] Traversal=PartKernel, AccType=Acc32
\t\tIFM Stripe   = [1, 49, 10, 1]
\t\tOFM Stripe   = [1, 49, 10, 140]
\t\tAssigned Cascade = 0
\t\tWeight buffer = 10816 bytes
\t\tDepth slices = [0, 16, 140]
\t\tEstimated Perf: Macs=2744000 Cycles=46040
"""

    def test_fields(self):
        import io, tempfile, os
        f = tempfile.NamedTemporaryFile("w", suffix=".log", delete=False)
        f.write(self.SAMPLE); f.close()
        ops = A.parse_schedule(f.name)
        os.unlink(f.name)
        self.assertEqual(len(ops), 1)
        o = ops[0]
        self.assertEqual(o["slices"], 2)
        self.assertEqual(o["ublock"], "[2, 2, 16]")
        self.assertEqual(o["vela_cycles"], 46040)
        self.assertIn("OFM[1, 24, 10, 16]", o["block"])
        self.assertIn("IFM[1, 49, 10, 1]", o["stripes"])

    def test_empty_rejects(self):
        import tempfile, os
        f = tempfile.NamedTemporaryFile("w", suffix=".log", delete=False)
        f.write("nothing here\n"); f.close()
        with self.assertRaises(A.Reject):
            A.parse_schedule(f.name)


if __name__ == "__main__":
    unittest.main(verbosity=1)
