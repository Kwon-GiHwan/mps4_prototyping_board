#!/usr/bin/env python3
"""Mutation/negative tests for pd_analyzer v2 (debug_db mapping)."""
import os
import tempfile
import unittest

import pd_analyzer as A


def prof(records, tail_total):
    lines = ["PLPROF_BEGIN,%d" % len(records)]
    for i, (c, e) in enumerate(records):
        lines.append("PLPROF,%d,%d,%s" % (i, c, ",".join(map(str, e))))
    lines.append("PLPROF_END")
    return {"plprof": "\n".join(lines), "pl_count": len(records),
            "total": tail_total}


class TestSegments(unittest.TestCase):
    def test_tail_added_when_one_short(self):
        s = A.segments(prof([(50, [1] * 5)], 70), 2)
        self.assertEqual([x["ccnt"] for x in s], [50, 70])
        self.assertTrue(s[1]["tail"])

    def test_exact_count_no_tail(self):
        s = A.segments(prof([(50, [1] * 5), (60, [2] * 5)], 999), 2)
        self.assertFalse(s[1]["tail"])
        self.assertEqual(s[1]["ccnt"], 60)

    def test_count_mismatch_rejects(self):
        with self.assertRaises(A.Reject):
            A.segments(prof([(50, [1] * 5)], 70), 4)

    def test_plcount_field_mismatch_rejects(self):
        p = prof([(50, [1] * 5)], 70)
        p["pl_count"] = 3
        with self.assertRaises(A.Reject):
            A.segments(p, 2)


class TestPerSource(unittest.TestCase):
    def cell(self):
        return {
            "queue": [(100, 1), (200, 2), (300, 3)],
            "optimised": {1: {"source_id": 10, "operator": "Add"},
                          2: {"source_id": 10, "operator": "Rescale"},
                          3: {"source_id": 11, "operator": "Conv2D"}},
            "source": {10: {"operator": "Add", "kernel": "1x1",
                            "ofm": "1x1x24", "ext_key": "5"},
                       11: {"operator": "Conv2D", "kernel": "3x3",
                            "ofm": "1x1x8", "ext_key": "6"}},
            "prof": prof([(10, [1] * 5), (20, [2] * 5)], 30),
        }

    def test_multi_launch_source_aggregation(self):
        agg = A.per_source(self.cell())
        self.assertEqual(agg[10]["ccnt"], 30)      # two launches summed
        self.assertEqual(agg[10]["launches"], 2)
        self.assertEqual(agg[10]["evt"], [3, 3, 3, 3, 3])
        self.assertEqual(agg[11]["ccnt"], 30)      # tail launch
        self.assertTrue(agg[11]["tail_in_op"])
        self.assertIsNone(agg[11]["evt"])

    def test_none_prof_passthrough(self):
        c = self.cell()
        c["prof"] = None
        self.assertIsNone(A.per_source(c))


class TestParseDb(unittest.TestCase):
    XML = """<x><table name="queue">
<![CDATA[
"offset","cmdstream_id","optimised_id","scheduled_id"
300,1,2,9
100,1,1,8
]]>
</table><table name="optimised">
<![CDATA[
"id","source_id","operator","kernel_w","kernel_h","ofm_w","ofm_h","ofm_d"
1,7,"Conv2D",3,3,4,4,8
2,7,"Rescale",1,1,4,4,8
]]>
</table><table name="source">
<![CDATA[
"id","operator","kernel_w","kernel_h","ofm_w","ofm_h","ofm_d","ext_key"
7,"Conv2D",3,3,4,4,8,"2"
]]>
</table></x>"""

    def test_queue_sorted_by_offset(self):
        f = tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False)
        f.write(self.XML); f.close()
        q, opt, src = A.parse_db(f.name)
        os.unlink(f.name)
        self.assertEqual(q, [(100, 1), (300, 2)])
        self.assertEqual(opt[2]["source_id"], 7)
        self.assertEqual(src[7]["ofm"], "4x4x8")

    def test_missing_table_rejects(self):
        f = tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False)
        f.write("<x></x>"); f.close()
        with self.assertRaises(A.Reject):
            A.parse_db(f.name)
        os.unlink(f.name)


if __name__ == "__main__":
    unittest.main(verbosity=1)
