"""firmware placement.c (Stage 4 placement comparison, docs/plan/stage4_memory_placement_plan.md F2, F3, F5) compiled for
the host with a probe that prints what it returns. Expected values are written out here from MLEK Dedicated_Sram's table
(QCONFIG 3, region 0 3, region 1 3, regions 2-7 1; SRAM placement: region 1 0, MLEK Shared_Sram's value), the FI101 map
(free SRAM from 0x31060000 to 0x31400000) and the Stage 4 conv_base record (model 0x70000000, arena 0x700015C0)."""
import pathlib, shutil, subprocess, tempfile, unittest
REPO = pathlib.Path(__file__).resolve().parents[2]
FW = REPO / "firmware" / "driver_runner"
UC = FW / "use_case" / "pmu_runner"
CC = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
OUT = {}


def setUpModule():
    if CC is None:
        raise unittest.SkipTest("no C compiler")
    with tempfile.TemporaryDirectory() as d:
        exe = pathlib.Path(d) / "probe"
        subprocess.run([CC, "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(UC / "include"), "-o", str(exe),
                        str(FW / "tests" / "placement_probe.c"), str(UC / "src" / "placement.c")], check=True)
        text = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
    for ln in text.splitlines():
        k, *v = ln.split()
        OUT[k] = [int(x, 0) for x in v]


class Select(unittest.TestCase):
    def test_table(self):
        ddr = {-2: 3, -1: 3, 0: 3, 1: 3, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 3}   # out of range: region 0's value
        for p, want in ((0, ddr), (1, {**ddr, 1: 0}), (2, ddr)):                 # 2: unknown -> never the SRAM port
            for i, v in want.items():
                self.assertEqual(OUT[f"select_{p}_{i}"], [v], (p, i))

    def test_regioncfg(self):
        self.assertEqual(OUT["regioncfg_0_5"], [0x15F])                          # conv_base, 5 bases (plan §1.1)
        self.assertEqual(OUT["regioncfg_1_5"], [0x153])
        self.assertEqual(OUT["regioncfg_0_3"], [0x1F])
        self.assertEqual(OUT["regioncfg_1_3"], [0x13])
        self.assertEqual(OUT["regioncfg_0_0"], [0])
        self.assertEqual(OUT["regioncfg_0_8"], [0x555F])
        self.assertEqual(OUT["regioncfg_0_9"], [0x555F])                          # 8 regions at most
        for n in range(10):
            a, b = OUT[f"regioncfg_0_{n}"][0], OUT[f"regioncfg_1_{n}"][0]
            self.assertEqual(a ^ b, 0xC if n >= 2 else 0, n)                       # only region 1's two bits differ


class SramArena(unittest.TestCase):
    def test_addresses(self):
        self.assertEqual(OUT["arena_0"], [0x310615C0])                           # the plan's address; low 16 bits 0x15C0
        self.assertEqual(OUT["arena_1"], [0x310715C0])                           # rounded up to the next 64 KiB
        self.assertEqual(OUT["arena_5"], [0x310615C0])                           # ends exactly at 0x31400000
        for k in (2, 3, 4, 6, 7):                                                # unaligned model, below, too long, empty
            self.assertEqual(OUT[f"arena_{k}"], [0], k)


class MemCheck(unittest.TestCase):
    def test_faults(self):
        self.assertEqual(OUT["check_0"], [0, -1])
        self.assertEqual(OUT["check_1"], [1, 100])                               # a word that does not hold the pattern
        self.assertEqual(OUT["check_2"], [1, 2048])                              # aliasing: the upper half echoes
        self.assertEqual(OUT["check_3"], [2, 100])                               # only the complement pass sees it
        self.assertEqual(OUT["get"], [1])


if __name__ == "__main__":
    unittest.main()
