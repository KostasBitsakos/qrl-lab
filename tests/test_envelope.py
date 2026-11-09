import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import envelope as E
from labdb import LabError

ENV = {"worktrees": ["code-poisson-c345"], "interpreters": ["/home/ubuntu/qrl-lab/.venv/bin/python"], "cpu_affinity": "8-39", "max_wall_hours": 12,
       "max_retries": 2, "max_parallel": 2, "cpu_hours_budget": 10}


def spec(**kw):
    s = {"name": "t", "scope": "sim", "cwd": "code-poisson-c345", "limits": {"wall_clock_hours": 1},
         "entries": [{"name": "a", "cmd": ["/home/ubuntu/qrl-lab/.venv/bin/python", "tuning/t12_unit.py"], "cpus": 2, "smoke": True}]}
    s.update(kw)
    return s


ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))


class T(unittest.TestCase):
    def setUp(self):
        self._lr, E.lab_root = E.lab_root, lambda: ROOT

    def tearDown(self):
        E.lab_root = self._lr

    def test_ok(self):
        E.check_spec(ENV, spec())

    def test_scope(self):
        with self.assertRaises(LabError):
            E.check_spec(ENV, spec(scope="real", real={"kube_context": "x", "namespace": "n", "rollback": "r"}))

    def test_cwd_outside(self):
        with self.assertRaises(LabError):
            E.check_spec(ENV, spec(cwd="tools"))

    def test_interpreter(self):
        s = spec(); s["entries"][0]["cmd"] = ["/tmp/python3", "x.py"]
        with self.assertRaises(LabError):
            E.check_spec(ENV, s)

    def test_dash_c(self):
        s = spec(); s["entries"][0]["cmd"] = ["/home/ubuntu/qrl-lab/.venv/bin/python", "-c", "x"]
        with self.assertRaises(LabError):
            E.check_spec(ENV, s)

    def test_script_outside(self):
        s = spec(); s["entries"][0]["cmd"] = ["/home/ubuntu/qrl-lab/.venv/bin/python", "../tools/envelope.py"]
        with self.assertRaises(LabError):
            E.check_spec(ENV, s)

    def test_no_smoke(self):
        s = spec(); s["entries"][0]["smoke"] = False
        with self.assertRaises(LabError):
            E.check_spec(ENV, s)

    def test_affinity(self):
        with self.assertRaises(LabError):
            E.check_spec(ENV, spec(cpu_affinity="0-3"))

    def test_nan_wall(self):
        with self.assertRaises(LabError):
            E.check_spec(ENV, spec(limits={"wall_clock_hours": float("nan")}))

    def test_wall(self):
        with self.assertRaises(LabError):
            E.check_spec(ENV, spec(limits={"wall_clock_hours": 99}))

    def test_need(self):
        self.assertEqual(E.need_cpu_h(spec()), 2.0)


if __name__ == "__main__":
    unittest.main()
