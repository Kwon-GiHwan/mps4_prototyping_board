import hashlib
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import Mock, patch

from host.campaigns.build import build, command
from host.campaigns.errors import CellFailure


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        model = self.root / "selected model.tflite"
        model.write_bytes(b"selected model bytes")
        for name in ("vela.ini", "toolchain.cmake"):
            (self.root / name).write_text("fixture")
        for args in (("init", "-q"), ("add", "selected model.tflite", "vela.ini", "toolchain.cmake"),
                     ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        self.tool = self.root / "tool"
        self.tool.write_text('''#!/usr/bin/env python3
import pathlib, sys
a=sys.argv[1:]
if '--version' in a: print('fixture version 1')
elif '--help' in a: print('--accelerator-config {ethos-u55-128}')
elif '--accelerator-config' in a:
    source=pathlib.Path(a[-1])
    pathlib.Path(a[a.index('--output-dir')+1],source.stem+'_vela.tflite').write_bytes(source.read_bytes()+b'compiled')
elif '-B' in a:
    b=pathlib.Path(a[a.index('-B')+1]);b.mkdir()
    defs=dict(x[2:].split('=',1) for x in a if x.startswith('-D'))
    defs.update(CMAKE_C_COMPILER=sys.argv[0],CMAKE_CXX_COMPILER=sys.argv[0])
    (b/'CMakeCache.txt').write_text(''.join(k+':STRING='+v+'\\n' for k,v in defs.items()))
    (b/'model_path').write_text(defs['inference_runner_MODEL_PATH'])
elif '--build' in a:
    b=pathlib.Path(a[a.index('--build')+1]);(b/'bin').mkdir()
    (b/'bin/mlek_inference_runner.axf').write_bytes(pathlib.Path((b/'model_path').read_text()).read_bytes()+b'axf')
''')
        self.tool.chmod(0o755)
        self.cell = {"model": {"path": str(model), "sha256": hashlib.sha256(model.read_bytes()).hexdigest()},
                     "target": {"npu": "ethos-u55", "platform": "mps3", "subsystem": "sse-300", "timing_adapter": "ON"},
                     "options": {"mac": 128, "activation_bytes": 2097152, "system_config": "test",
                                 "memory_mode": "Shared_Sram", "optimise": "Performance"}}
        self.config = {"build": {"mlek_root": str(self.root), "vela": str(self.tool), "cmake": str(self.tool),
                                 "vela_config": "vela.ini", "toolchain_file": "toolchain.cmake", "epoch": 1,
                                 "jobs": 1, "timeout_seconds": 5}}

    def test_model_injected_and_both_timing_states_verified(self):
        for state in ("ON", "OFF"):
            self.cell["target"]["timing_adapter"] = state
            result = build(self.cell, self.config, self.root / state)
            self.assertEqual(Path(result["axf"]).read_bytes(), b"selected model bytescompiledaxf")
            self.assertEqual(result["resolved"]["timing_adapter"], state)
            self.assertTrue(result["tools"]["vela"]["sha256"])
            self.assertEqual(result["deployable_hashes"]["mlek_inference_runner.axf"], result["hashes"]["axf"])
            self.assertEqual(result["resolved"]["source_identity"], "VERIFIED_GIT_SOURCE")

    def test_failure_and_no_stale_reuse(self):
        directory = self.root / "output"
        build(self.cell, self.config, directory)
        with self.assertRaises(CellFailure):
            build(self.cell, self.config, directory)
        self.cell["model"]["sha256"] = "0" * 64
        with self.assertRaises(CellFailure) as error:
            build(self.cell, self.config, self.root / "hash")
        self.assertEqual(error.exception.status, "IDENTITY_MISMATCH")

    def test_compiler_failure_preserves_log(self):
        self.tool.write_text(self.tool.read_text().replace("source=pathlib.Path(a[-1])", "print('out of memory');sys.exit(2);source=pathlib.Path(a[-1])"))
        with self.assertRaises(CellFailure) as error:
            build(self.cell, self.config, self.root / "failure")
        self.assertEqual(error.exception.status, "MEMORY_ERROR")
        self.assertIn("out of memory", (self.root / "failure/vela.log").read_text())

    def test_timing_mismatch_and_option_override_fail(self):
        self.tool.write_text(self.tool.read_text().replace("(b/'CMakeCache.txt').write_text", "defs['ETHOS_U_NPU_TIMING_ADAPTER_ENABLED']='OFF';(b/'CMakeCache.txt').write_text"))
        with self.assertRaises(CellFailure) as error:
            build(self.cell, self.config, self.root / "ta")
        self.assertEqual(error.exception.status, "IDENTITY_MISMATCH")
        self.cell["options"]["cmake_options"] = {"inference_runner_MODEL_PATH:FILEPATH": "/other"}
        with self.assertRaises(CellFailure) as error:
            build(self.cell, self.config, self.root / "override")
        self.assertIn("Reserved", str(error.exception))

    def test_resolved_model_override_is_rejected(self):
        self.tool.write_text(self.tool.read_text().replace("(b/'CMakeCache.txt').write_text", "defs['inference_runner_MODEL_PATH']='/other/model';(b/'CMakeCache.txt').write_text"))
        with self.assertRaises(CellFailure) as error:
            build(self.cell, self.config, self.root / "override")
        self.assertEqual(error.exception.status, "IDENTITY_MISMATCH")
        self.assertIn("MODEL_PATH", str(error.exception))

    def test_inputs_changed_while_building_are_rejected(self):
        original = self.tool.read_text()
        for name in ("selected model.tflite", "vela.ini", "toolchain.cmake"):
            with self.subTest(name=name):
                path = self.root / name
                before = path.read_bytes()
                self.tool.write_text(original.replace("source=pathlib.Path(a[-1])", f"pathlib.Path({str(path)!r}).write_bytes(b'changed');source=pathlib.Path(a[-1])"))
                with self.assertRaises(CellFailure) as error:
                    build(self.cell, self.config, self.root / (name + ".build"))
                self.assertEqual(error.exception.status, "IDENTITY_MISMATCH")
                path.write_bytes(before)

    def test_keyboard_interrupt_kills_and_reaps_command(self):
        process = Mock(pid=1234)
        process.wait.side_effect = [KeyboardInterrupt, 0]
        with patch('host.campaigns.build.subprocess.Popen', return_value=process), \
                patch('host.campaigns.build.os.killpg') as kill:
            with self.assertRaises(KeyboardInterrupt):
                command(["tool"], self.root, "interrupted", 1)
        kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)

    def test_unidentified_source_and_parent_repository_rejected(self):
        self.config["build"]["mlek_root"] = str(self.root / "child")
        (self.root / "child").mkdir()
        self.config["build"]["vela_config"] = str(self.root / "vela.ini")
        self.config["build"]["toolchain_file"] = str(self.root / "toolchain.cmake")
        with self.assertRaises(CellFailure) as error:
            build(self.cell, self.config, self.root / "parent")
        self.assertEqual(error.exception.status, "ENVIRONMENT_UNAVAILABLE")
        (self.root / ".git").rename(self.root / "git-backup")
        self.config["build"]["mlek_root"] = str(self.root)
        with self.assertRaises(CellFailure) as error:
            build(self.cell, self.config, self.root / "nongit")
        self.assertEqual(error.exception.status, "ENVIRONMENT_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
