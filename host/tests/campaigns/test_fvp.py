import hashlib
from pathlib import Path
import tempfile
import unittest

from host.campaigns.errors import CellFailure
from host.campaigns.fvp import run_fvp


class FvpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        axf = self.root / "model.axf"
        axf.write_bytes(b"axf")
        self.tool = self.root / "fvp"
        self.cell = {"target": {"executable": str(self.tool), "board_prefix": "mps3_board", "mac_parameter": "ethosu.num_macs"},
                     "options": {"mac": 128}}
        self.config = {"measurement": {"timeout_seconds": 0.15}}
        self.artifacts = {"axf": str(axf), "hashes": {"axf": hashlib.sha256(b"axf").hexdigest()}}

    def fake(self, content, suffix="time.sleep(5)"):
        self.tool.write_text('''#!/usr/bin/env python3
import pathlib, sys, time
if '--version' in sys.argv or '--list-params' in sys.argv:
    print('fixture');sys.exit(0)
path=next(a.split('=',1)[1] for a in sys.argv if '.uart0.out_file=' in a)
pathlib.Path(path).write_text(%r)
%s
''' % (content, suffix))
        self.tool.chmod(0o755)

    def test_success_retains_uart_and_stops_owned_process(self):
        text = "Total number of inferences: 1\nInference completed.\n"
        self.fake(text)
        result = run_fvp(self.cell, self.config, self.artifacts, self.root / "run")
        self.assertEqual(result["uart"], text)
        self.assertEqual(Path(result["uart_path"]).read_text(), text)
        self.assertIn("executable_identity", result)

    def test_memory_timeout_exit_and_invalid_count(self):
        cases = [("Failed to allocate tensors", "time.sleep(5)", "MEMORY_ERROR"),
                 ("", "time.sleep(5)", "TIMEOUT"),
                 ("", "sys.exit(3)", "EXECUTION_ERROR"),
                 ("Inference completed.\nTotal number of inferences: 2", "time.sleep(5)", "INVALID_MEASUREMENT"),
                 ("Inference completed.\nTotal number of inferences: 1", "sys.exit(3)", "EXECUTION_ERROR")]
        for i, (text, suffix, status) in enumerate(cases):
            with self.subTest(status=status, suffix=suffix):
                self.fake(text, suffix)
                directory = self.root / str(i)
                with self.assertRaises(CellFailure) as error:
                    run_fvp(self.cell, self.config, self.artifacts, directory)
                self.assertEqual(error.exception.status, status)
                self.assertTrue((directory / "uart.txt").exists())

    def test_modified_artifact_rejected(self):
        self.fake("")
        Path(self.artifacts["axf"]).write_bytes(b"wrong")
        with self.assertRaises(CellFailure) as error:
            run_fvp(self.cell, self.config, self.artifacts, self.root / "run")
        self.assertEqual(error.exception.status, "IDENTITY_MISMATCH")


if __name__ == "__main__":
    unittest.main()
