"""board/sudo_session.sh: the session check, the step order, and the restore after a failure. The board scripts are
stubs that log their arguments (EVS_DIR); SESSION_TEST=1 runs user steps without runuser and skips the root check."""
import os, pathlib, subprocess, tempfile, unittest
REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "board" / "sudo_session.sh"
STUB = '#!/bin/sh\necho "{name} $*" >> "$EVS_DIR/calls.log"\n[ "${{FAIL_ON:-}}" = "{name} $*" ] && exit 7\nexit 0\n'


class Session(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.d = pathlib.Path(self.t.name)
        for n in ("deploy_mlek", "restore_mlek", "deploy", "restore"):
            (self.d / f"{n}.sh").write_text(STUB.format(name=n))

    def tearDown(self):
        self.t.cleanup()

    def sh(self, *args, test=True, **env):
        e = dict(os.environ, EVS_DIR=str(self.d), **env)
        if test:
            e["SESSION_TEST"] = "1"
        return subprocess.run(["sh", str(SCRIPT), *args], capture_output=True, text=True, env=e)

    def session(self, text):
        f = self.d / "s.txt"; f.write_text(text); return str(f)

    def calls(self):
        p = self.d / "calls.log"
        return p.read_text().splitlines() if p.exists() else []

    def test_check_accepts_a_balanced_session(self):
        f = self.session("# c\n\ndeploy_mlek /s /ev1\nuser echo hi\nrestore_mlek /ev1 /s\ndeploy /a /ev2\nrestore /ev2\n")
        r = self.sh("--check", f)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("SESSION OK", r.stdout)

    def test_check_refusals(self):
        for text in ("deploy_mlek /s /ev\nuser true\n",                        # ends with the image on the card
                     "deploy_mlek /s /ev\nrestore_mlek /other /s\n",           # restores something else
                     "deploy_mlek /s /ev\ndeploy /a /ev2\nrestore /ev2\nrestore_mlek /ev /s\n",   # two at once
                     "restore /ev\n",                                          # nothing deployed
                     "sudo rm -rf /\n",                                        # unknown step
                     "user\n",                                                 # empty user step
                     "deploy /a\nrestore /a\n"):                               # wrong arity
            r = self.sh("--check", self.session(text))
            self.assertNotEqual(r.returncode, 0, text)
            self.assertIn("FAIL", r.stdout, text)

    def test_runs_steps_in_order(self):
        f = self.session("deploy_mlek /s /ev\nuser echo \"user $(pwd)\" >> calls.log\nrestore_mlek /ev /s\n")
        r = self.sh("--run", f)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.calls(), ["deploy_mlek /s /ev", f"user {self.d}", "restore_mlek /ev /s"])
        self.assertIn("SESSION DONE", r.stdout)

    def test_failure_after_deploy_restores_then_stops(self):
        f = self.session("deploy_mlek /s /ev\nuser exit 3\nuser echo late >> calls.log\nrestore_mlek /ev /s\n")
        r = self.sh("--run", f)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.calls(), ["deploy_mlek /s /ev", "restore_mlek /ev /s"])
        self.assertIn("SESSION FAILED at step 2", r.stdout)

    def test_failed_deploy_is_not_restored(self):
        f = self.session("deploy /a /ev\nrestore /ev\n")
        r = self.sh("--run", f, FAIL_ON="deploy /a /ev")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.calls(), ["deploy /a /ev"])

    def test_app_deploy_recovery_uses_restore(self):
        f = self.session("deploy /a /ev\nuser false\nrestore /ev\n")
        self.sh("--run", f)
        self.assertEqual(self.calls(), ["deploy /a /ev", "restore /ev"])

    def test_refuses_without_root(self):
        r = self.sh(self.session("user true\n"), test=False)
        if os.geteuid() == 0:
            self.skipTest("running as root")
        self.assertEqual(r.returncode, 2)
        self.assertIn("run with sudo", r.stdout)


if __name__ == "__main__":
    unittest.main()
