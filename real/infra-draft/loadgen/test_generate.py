"""Offline contract checks; synthetic samples are unit tests, not calibration."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from scipy.stats import kstest

from generate import schedule
from sim_poisson_ms import PoissonMSEnv

ROOT = Path(__file__).resolve().parents[3]


class GeneratorTests(unittest.TestCase):
    def test_exact_simulator_parity(self):
        # Independent live-source import, catches stale vendor or RNG/reset drift.
        path = ROOT / "code-poisson-c345/tuning/poisson_ms.py"
        spec = importlib.util.spec_from_file_location("j352_reference_sim", path)
        ref = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = ref
        spec.loader.exec_module(ref)
        for seed in (0, 17, 2026):
            env = ref.PoissonMSEnv(seed=seed)
            env.reset()
            actual = list(schedule(seed, 100, 0.25))
            index = 0
            for tick in range(100):
                lam, offsets = env.wl.next_tick()
                for offset in offsets:
                    row = actual[index]
                    self.assertEqual(row['tick'], tick)
                    self.assertEqual(row['offset'], offset)
                    self.assertEqual(row['lambda_per_tick'], lam)
                    self.assertEqual(row['scheduled_seconds'], (tick + offset) * 0.25)
                    index += 1
            self.assertEqual(index, len(actual))

    def test_reproducible_and_distinct(self):
        a = list(schedule(17, 8, 1))
        self.assertEqual(a, list(schedule(17, 8, 1)))
        self.assertNotEqual(a, list(schedule(18, 8, 1)))
        scaled = list(schedule(17, 8, 2))
        self.assertEqual([r['offset'] for r in a], [r['offset'] for r in scaled])
        self.assertEqual([2*r['scheduled_seconds'] for r in a], [r['scheduled_seconds'] for r in scaled])

    def test_bounds_and_resp(self):
        rows = list(schedule(11, 20, 0.5))
        times = [r['scheduled_seconds'] for r in rows]
        self.assertEqual(times, sorted(times))
        for i, row in enumerate(rows):
            self.assertTrue(0 <= row['offset'] < 1)
            self.assertTrue(0 <= row['scheduled_seconds'] < 10)
            key = f'qrl-calib:11:{i}'.encode()
            expected = b'*3\r\n$3\r\nSET\r\n$'+str(len(key)).encode()+b'\r\n'+key+b'\r\n$1\r\nx\r\n'
            self.assertEqual(bytes.fromhex(row['resp_hex']), expected)

    def test_homogeneous_statistics(self):
        rows = list(schedule(123, 600, 1, 'poisson_hom'))
        counts = np.bincount([r['tick'] for r in rows], minlength=600)
        # 60 req/tick from Params; broad fixed diagnostic tolerances, no research claim.
        self.assertLess(abs(float(counts.mean()) - 60), 2)
        self.assertTrue(0.8 < counts.var()/counts.mean() < 1.2)
        times = np.array([r['scheduled_seconds'] for r in rows])
        self.assertGreater(kstest(np.diff(times), 'expon', args=(0, 1/60)).pvalue, 0.01)

    def test_modulation_overdispersed(self):
        workload = PoissonMSEnv(seed=123).wl
        counts = np.array([len(workload.next_tick()[1]) for _ in range(5000)])
        self.assertGreater(counts.var()/counts.mean(), 1)

    def test_invalid_inputs(self):
        for seed, ticks, seconds in ((-1, 1, 1), (True, 1, 1), (1, 0, 1), (1, 1, 0), (1, 1, float('nan')), (1, 1, float('inf'))):
            with self.assertRaises(ValueError):
                list(schedule(seed, ticks, seconds))

    def test_cli_metadata_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.lab/j352') as tmp:
            output = Path(tmp)/'requests.jsonl'
            cmd = [sys.executable, str(Path(__file__).with_name('generate.py')), '--seed', '17', '--ticks', '2', '--tick-seconds', '0.5', '--output', str(output)]
            subprocess.run(cmd, check=True, capture_output=True)
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            meta = json.loads(output.with_suffix('.jsonl.meta.json').read_text())
            self.assertEqual(meta['request_count'], len(rows))
            self.assertEqual(meta['transport'], 'offline only')
            before = output.read_bytes()
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(before, output.read_bytes())


if __name__ == '__main__':
    result = unittest.main(exit=False).result
    if not result.wasSuccessful():
        sys.exit(1)
    print("REQUEST_GENERATOR_OK")
