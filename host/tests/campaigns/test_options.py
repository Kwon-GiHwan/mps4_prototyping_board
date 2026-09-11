import unittest

from host.campaigns.errors import CellFailure
from host.campaigns.options import validate_options


class OptionsTests(unittest.TestCase):
    def test_supported_typed_values(self):
        validate_options({}, {"vela_options": ["--arena-cache-size=0", "--tensor-allocator", "HillClimb",
                                                "--cpu-tensor-alignment", "16", "--show-cpu-operations"],
                              "cmake_options": {"CMAKE_BUILD_TYPE": "Release"},
                              "fvp_parameters": {"mps3_board.oscclk": 100000000}})

    def test_vela_rejects_positional_abbreviation_and_malformed_values(self):
        for argv in (["other.tflite"], ["--accelerator-conf=ethos-u85-256"], ["--config", "evil.ini"],
                     ["--tensor-allocator", "Other"], ["--arena-cache-size", "-1"],
                     ["--cpu-tensor-alignment", "3"], ["--verbose-all=true"],
                     ["--recursion-limit"], ["--arena-cache-size", "0", "--arena-cache-size=4"]):
            with self.subTest(argv=argv), self.assertRaises(CellFailure):
                validate_options({}, {"vela_options": argv})

    def test_cmake_rejects_hooks_typed_keys_and_managed_board_flag(self):
        for key in ("CMAKE_PROJECT_INCLUDE", "CMAKE_BUILD_TYPE:STRING", "FPGA_PLATFORM_SSE_320",
                    "inference_runner_MODEL_PATH", "ETHOS_U_NPU_CONFIG_ID"):
            with self.subTest(key=key), self.assertRaises(CellFailure):
                validate_options({"cmake_options": {key: "ON"}}, {})

    def test_fvp_rejects_wildcards_managed_keys_and_nonscalars(self):
        for key, value in (("*.num_macs", 512), ("ethosu.num_macs", 512),
                           ("mps3_board.uart0.out_file", "other"), ("x=1", 2),
                           ("x", {}), ("x", "a\nb")):
            with self.subTest(key=key), self.assertRaises(CellFailure):
                validate_options({}, {"fvp_parameters": {key: value}})


if __name__ == "__main__":
    unittest.main()
