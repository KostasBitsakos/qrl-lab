"""C345 (J350): sandbox_guard profile for code-poisson-c345, generalised driver, W draft builder. No launches."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import importlib.util  # noqa: E402

import sandbox_guard as G  # noqa: E402


def _load(name):
    """Load tools/c345/<name>.py under a unique module name (tools/spiky_stage1 also has driver.py/build.py)."""
    key = f"c345_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, ROOT / "tools/c345" / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[key] = mod
        spec.loader.exec_module(mod)
    return sys.modules[key]


def test_profiles_keep_old_pins():
    assert G.profile({"repo": "code-poisson-spiky"}) == (G.SPIKY_ENV_COMMIT, G.SPIKY_HARNESS_COMMIT, G.SPIKY_ENTRY_SHA256)
    assert G.profile({"repo": "code-poisson"}) == (G.CYCLE2_ENV_COMMIT, G.CYCLE2_HARNESS_COMMIT, G.CYCLE2_ENTRY_SHA256)
    assert G.profile({"repo": G.C345_REPO})[1] == G.C345_HARNESS_COMMIT
    assert G.SANDBOX_BRANCHES[G.C345_REPO] == "dinos-poisson-c345" and G.C345_REPO in G.MANIFEST_REPOS


@pytest.mark.skipif(not (ROOT / "code-poisson-c345").is_dir(), reason="c345 worktree absent")
def test_w_draft_builds_and_validates():
    B, D = _load("build_w"), _load("driver")
    spec = B.build(("opus",))
    assert len(spec["tasks"]) == 1 + 10 * 2 * 2
    assert {t["seed"] for t in spec["tasks"] if t["stage"] == "W"} == {18500, 18501}
    assert [14000, 14019] in spec["sandbox"]["seed_ranges_forbidden"]
    assert spec["reserved_cpu_h"] <= spec["sandbox"]["cpu_hours_budget"] <= 160
    for t in spec["tasks"]:
        c = t["child"]["entries"][0]["cmd"]
        if t["stage"] == "W":
            assert c[c.index("--total-ticks") + 1] == "19968"
            assert "pms:poisson_ms" in c and "pms:poisson_ms_spiky" not in c
            assert ("--derp-double" in c) == (t["arm"] == "derp_ddqn")
            if "--pretrain-ticks" in c:
                assert c[c.index("--pretrain-ticks") + 1] == c[c.index("--finetune-ticks") + 1] == "9984"
    D.validate(spec, protected=True)
    bad = dict(spec, tasks=spec["tasks"][:-1])
    with pytest.raises(Exception):
        D.validate(bad, protected=False)


SMOKE = ROOT / ".lab/j350/smoke_out"


def _artifact_case(tmp_path, name, mutate=None):
    import json
    D = _load("driver")
    from labdb import LabError  # noqa: F401
    x = json.loads((SMOKE / f"{name}.json").read_text())
    cmd = json.loads((SMOKE / f"{name}.cmd").read_text())
    if mutate:
        mutate(x)
    (tmp_path / "w").mkdir(exist_ok=True)
    (tmp_path / "w" / "a.json").write_text(json.dumps(x))
    arm = name.split("-")[3]
    tgt = int(cmd[cmd.index("--checkpoints") + 1])
    D.SPEC.clear()
    D.SPEC.update(variant="pms:poisson_ms", val_seeds=list(range(13000, 13020)))
    t = dict(stage="W", arm=arm, seed=18500, mode="off", out="a.json", target_ticks=tgt, child=dict(cwd="w", entries=[dict(cmd=cmd)]))
    D.artifact(t, root=tmp_path)


@pytest.mark.skipif(not SMOKE.is_dir(), reason="J350 smoke outputs absent")
@pytest.mark.parametrize("name,mutate", [
    ("c345-W-opus-derp_ddqn-c0-s18500", lambda x: x.update(double_dqn_target=None)),        # plain DERP artifact
    ("c345-W-opus-derp_ddqn-c0-s18500", lambda x: x.update(derp_history=1)),                # wrong history
    ("c345-W-opus-derp_ddqn-c1-s18500", lambda x: x.update(target_sync_replays=1)),         # wrong sync
    ("c345-W-astra-lstm_transfer-c1-s18500", lambda x: x.update(pretrain_variant="spike300_d5")),  # wrong source
    ("c345-W-astra-lstm_transfer-c1-s18500", lambda x: x.update(finetune_eps="restart")),
    ("c345-W-astra-lstm-c1-s18500", lambda x: x.update(target_sync_replays=250)),           # wrong optimiser cfg
])
def test_artifact_provenance_mutations(tmp_path, name, mutate):
    from labdb import LabError
    _artifact_case(tmp_path, name)                  # the genuine artifact is accepted
    with pytest.raises(LabError):
        _artifact_case(tmp_path, name, mutate)
