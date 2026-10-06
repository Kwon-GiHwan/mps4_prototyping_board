import difflib, hashlib, pathlib, sys, unittest
HERE = pathlib.Path(__file__).parent; sys.path.insert(0, str(HERE))
import patch_u85_vendor_timeout as V
RAW = (HERE.parent / "Drivers" / "u85_driver" / "u85.c").read_bytes()
BASE = RAW.decode()   # bytes -> str without newline translation: the file is CRLF


class T(unittest.TestCase):
    def test_pinned(self): self.assertEqual(hashlib.sha256(RAW).hexdigest(), V.VENDOR_SHA256)

    def test_crlf_preserved(self):
        g = V.generate(BASE)
        self.assertIn("\r\n", BASE)
        self.assertEqual(g.count("\r\n"), BASE.count("\r\n"))

    def test_exactly_one_line_changes(self):
        g = V.generate(BASE)
        d = [l for l in difflib.unified_diff(BASE.split("\r\n"), g.split("\r\n"), lineterm="", n=0)
             if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        self.assertEqual(d, ["-#define BUSY_SLEEP_TIMEOUT 10000",
                             "+#define BUSY_SLEEP_TIMEOUT 200000000 /* Tier C step 1: was 10000 */"])

    def test_refuses_missing_anchor(self):
        with self.assertRaises(SystemExit): V.generate(BASE.replace("BUSY_SLEEP_TIMEOUT 10000", "BUSY_SLEEP_TIMEOUT 10001", 1))


if __name__ == "__main__":
    unittest.main()
