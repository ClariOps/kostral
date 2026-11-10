"""Remote engines: start the three example servers, run the remote workflow."""
import json
import socket
import subprocess
import sys
import time
import unittest

from .helpers import EXIT_CRASH, ROOT, koss
import os

PORTS = (9001, 9002, 9003)
SERVERS = ("optimizer_server.py", "validator_server.py", "security_server.py")


def _port_open(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


class RemoteNotRunningTests(unittest.TestCase):
    def test_remote_run_with_servers_down_fails_loudly(self):
        """A missing engine must be an error, never an empty report."""
        if any(_port_open(p) for p in PORTS):
            self.skipTest("ports 9001-9003 are already in use")
        res = koss("remote", "examples/demo/bad.yaml", "--exec", "examples/remote/workflow.py",
                   "--output", "json")
        self.assertEqual(res.rc, EXIT_CRASH, str(res))   # distinct from 1 = findings
        self.assertNotIn('"status"', res.out)


class RemoteRoundTripTests(unittest.TestCase):
    procs = []

    @classmethod
    def setUpClass(cls):
        if any(_port_open(p) for p in PORTS):
            raise unittest.SkipTest("ports 9001-9003 are already in use")
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        for script in SERVERS:
            cls.procs.append(subprocess.Popen(
                [sys.executable, str(ROOT / "examples/remote" / script)], cwd=str(ROOT), env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        deadline = time.time() + 15
        while time.time() < deadline and not all(_port_open(p) for p in PORTS):
            time.sleep(0.2)
        if not all(_port_open(p) for p in PORTS):
            cls.tearDownClass()
            raise unittest.SkipTest("example servers did not start")

    @classmethod
    def tearDownClass(cls):
        for p in cls.procs:
            p.terminate()
        for p in cls.procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        cls.procs = []

    def _remote(self, rel):
        return koss("remote", rel, "--exec", "examples/remote/workflow.py", "--output", "json")

    def test_remote_result_matches_local_result(self):
        for rel in ("examples/demo/bad.yaml", "examples/demo/good.yaml", "examples/demo/security.yaml"):
            with self.subTest(file=rel):
                remote = self._remote(rel)
                local = koss("optimize", rel, "--dry-run", "--output", "json")
                self.assertEqual(remote.rc, local.rc, str(remote))
                self.assertEqual(json.loads(remote.out), json.loads(local.out))

    def test_remote_output_is_deterministic(self):
        a = self._remote("examples/demo/bad.yaml")
        b = self._remote("examples/demo/bad.yaml")
        self.assertEqual(a.rc, b.rc, str(a))
        self.assertIn(a.rc, (0, 1), str(a))
        self.assertEqual(a.out, b.out)


if __name__ == "__main__":
    unittest.main()
