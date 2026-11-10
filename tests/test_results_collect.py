import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import results_collect as rc


def _fake_root(tmp_path):
    for batch, label, src, *_ in rc.MANIFEST:
        p = tmp_path / src
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
    seeds = {"1": 1.0, "2": 2.0}
    (tmp_path / ".lab/j442/summary.json").write_text(json.dumps({"dinos": {"seeds": seeds}}))
    for s in (".lab/c401/f_analysis.json", ".lab/j414/t12_analysis.json"):
        (tmp_path / s).write_text(json.dumps({"arms": {"dinos": {"seed_means": seeds}}}))
    (tmp_path / ".lab/j450/T-summary.json").write_text(json.dumps({"groups": {"w": {"dinos": {"per_seed": seeds}}}}))
    return tmp_path


def test_build_idempotent_and_copy_only(tmp_path):
    root = _fake_root(tmp_path / "r"); out = tmp_path / "out"
    files, missing = rc.build(root, out)
    assert not missing and (out / "README.md").exists()
    assert (out / "5_S_spiky_10seeds/S_per_seed_val.csv").read_text().splitlines()[1] == "dinos,1,1.0"
    first = (out / "MANIFEST.json").read_text()
    rc.build(root, out)
    assert (out / "MANIFEST.json").read_text() == first
    assert "3_test12_poisson_ms/j414_t12_analysis.json" in files


def test_missing_source_reported_not_invented(tmp_path):
    root = tmp_path / "r"; root.mkdir()
    files, missing = rc.build(root, tmp_path / "out")
    assert not files and len(missing) >= len(rc.MANIFEST)
    assert "ΛΕΙΠΕΙ" in (tmp_path / "out/README.md").read_text()
