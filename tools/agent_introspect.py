#!/usr/bin/env python3
"""Describe the Q-network and the hyperparameters of one tuning agent WITHOUT training (dashboard «📈 Πειράματα»).

  taskset -c 0-7 .venv/bin/python tools/agent_introspect.py --agent derp --agent-variant verbatim --state-size 7 \
      [--derp-history 1] [--transfer]

Builds the agent object of code-tuning/tuning/legacy (the same constructors c5_protocol.run_c5 uses) on CPU, inside
torch.random.fork_rng (no global RNG is touched; nothing is trained or saved), and prints one JSON:
  hyper: {name: {value, source}}  (source = file:line of the assignment, found in the class source)
  layers: [{name, type, in, out, units, num_layers, activation, connection}]  (from named_modules / forward source)
  n_params (trainable, online network), reward lines of the env files (file:line).
Values that cannot be determined are left out; the dashboard then shows «άγνωστο».
"""
import argparse
import inspect
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CODE = os.path.join(ROOT, "code-tuning")


def _src_line(obj, pattern):
    """file:line (relative to code-tuning) of the first source line of obj matching the regex, else None."""
    try:
        lines, start = inspect.getsourcelines(obj)
        start = max(start, 1)      # modules report 0
        f = os.path.relpath(inspect.getsourcefile(obj), CODE)
    except (OSError, TypeError):
        return None
    rx = re.compile(pattern)
    for i, ln in enumerate(lines):
        if rx.search(ln):
            return f"{f}:{start + i}"
    return None


def _file_lines(path, pattern):
    out = []
    rx = re.compile(pattern)
    try:
        with open(path) as fh:
            for i, ln in enumerate(fh, 1):
                if rx.search(ln):
                    out.append({"line": ln.strip(), "source": f"{os.path.relpath(path, CODE)}:{i}"})
    except OSError:
        pass
    return out


def build(agent, variant, state_size, hist=1, transfer=False):
    import torch
    from tuning.legacy import agent_dense_fixed as DFX
    from tuning.legacy import agent_huber, agent_huber_transfer, ddqnagent
    from tuning.legacy import agent_lstm_fixed as FX
    from tuning.legacy import run_legacy as RL
    torch.set_num_threads(1)
    with torch.random.fork_rng(devices=[]):
        if agent == "derp":
            a, cls = ddqnagent.DDQNAgent(hist * state_size, RL.ACTIONS), ddqnagent.DDQNAgent
        elif variant == "dense_fixed":
            a, cls = DFX.make_scratch(state_size, RL.ACTIONS, RL.SEQ), FX.FixedLSTMAgent
        elif variant == "fixed":
            a, cls = FX.make_scratch(state_size, RL.ACTIONS, RL.SEQ), FX.FixedLSTMAgent
            if agent == "dinos_t" and transfer:
                a = FX.make_transfer(state_size, RL.ACTIONS, RL.SEQ, a.online_model.state_dict())
        elif agent == "dinos_t":
            a, cls = agent_huber_transfer.DDQNAgentLSTM(state_size, RL.ACTIONS, RL.SEQ), agent_huber_transfer.DDQNAgentLSTM
        else:
            a, cls = agent_huber.DDQNAgent(state_size, RL.ACTIONS, RL.SEQ), agent_huber.DDQNAgent
    return a, cls


def describe(agent, variant, state_size, hist=1, transfer=False):
    sys.path.insert(0, CODE)
    from tuning.legacy import run_legacy as RL
    a, cls = build(agent, variant, state_size, hist, transfer)
    hyper = {}

    def put(name, value, obj, pat):
        hyper[name] = {"value": value, "source": _src_line(obj, pat)}
    put("gamma", float(a.gamma), cls, r"self\.gamma\s*=")
    put("memory (replay capacity)", int(a.memory.maxlen), cls, r"self\.memory\s*=")
    put("learning_rate (constructor)", float(a.learning_rate), cls, r"self\.learning_rate\s*=")
    put("epsilon_decay (constructor)", float(a.epsilon_decay), cls, r"self\.epsilon_decay\s*=")
    put("optimizer", type(a.optimizer).__name__, cls, r"self\.optimizer\s*=")
    put("loss", type(a.criterion).__name__, cls, r"self\.criterion\s*=")
    hyper["batch_size"] = {"value": RL.BATCH, "source": _src_line(RL, r"^STATE, ACTIONS, SEQ, BATCH")}
    if hasattr(a, "target_sync"):
        hyper["target_sync (default, replays)"] = {"value": int(a.target_sync), "source": _src_line(cls, r"self\.target_sync\s*=")}
    else:
        hyper["target_sync"] = {"value": "after every replay",
                                 "source": _src_line(cls.replay, r"self\.update_target_model\(\)\s*$")}
    if hasattr(a, "ddqn_target"):
        hyper["target rule"] = {"value": "Double DQN: a*=argmax Q_online(s'), y=r+γ·Q_target(s',a*) (detached)",
                                "source": _src_line(cls, r"def ddqn_target")}
    else:
        hyper["target rule"] = {"value": "y=r+γ·max_a Q_target(s',a) (no Double-DQN argmax)",
                                "source": _src_line(cls, r"torch\.max\(self\.target_model")}
    m = a.online_model
    fwd = ""
    try:
        fwd = inspect.getsource(type(m).forward)
    except (OSError, TypeError):
        pass
    layers = []
    for name, mod in m.named_modules():
        t = type(mod).__name__
        if name == "" or t in ("ReLU", "Tanh", "Sigmoid", "MyDenseNet"):
            continue
        row = {"name": name, "type": t}
        if t == "Linear":
            row.update({"in": mod.in_features, "out": mod.out_features, "units": mod.out_features,
                        "connection": "fully connected (dense)"})
        elif t == "LSTM":
            row.update({"in": mod.input_size, "units": mod.hidden_size, "num_layers": mod.num_layers,
                        "connection": "recurrent, stacked layers, batch_first=%s" % mod.batch_first,
                        "activation": "tanh/sigmoid gates (PyTorch LSTM)"})
        layers.append(row)
    # activation after each Linear: read from the forward source of the module that owns it
    owner = getattr(m, "net", m)
    try:
        ofwd = inspect.getsource(type(owner).forward)
    except (OSError, TypeError):
        ofwd = fwd
    for row in layers:
        if row["type"] == "Linear":
            leaf = row["name"].split(".")[-1]
            pos = ofwd.find(f"self.{leaf}(")
            nxt = ofwd[pos:].split("\n", 3)[1:3] if pos >= 0 else []
            row["activation"] = "ReLU" if any("relu" in x for x in nxt) else ("none (Q-values out)" if pos >= 0 else None)
    if "reshape" in fwd:
        layers.insert(0, {"name": "(input)", "type": "Flatten", "connection": "flatten 10 x F window row-major"})
    from tuning.legacy import orig_variants as OV
    feats = {"orig": {"value": list(OV.FEATURES), "source": _src_line(OV, r"^FEATURES\s*=")},
             "orig_delay": {"value": list(OV.FEATURES_DELAY), "source": _src_line(OV, r"^FEATURES_DELAY\s*=")}}
    return {"agent": agent, "agent_variant": variant, "features": feats, "state_size": state_size, "derp_history": hist, "transfer": transfer,
            "class": f"{cls.__module__}.{cls.__name__}", "network": type(m).__name__,
            "network_source": _src_line(type(m), r"class "), "hyper": hyper, "layers": layers,
            "n_params": int(sum(p.numel() for p in m.parameters() if p.requires_grad)),
            "reward_lines": {
                "orig": _file_lines(os.path.join(CODE, "tuning/legacy/env_orig.py"), r"reward\s*=") +
                        _file_lines(os.path.join(CODE, "tuning/legacy/orig_variants.py"), r"reward\s*=\s*served"),
                "lstm_transfer": _file_lines(os.path.join(CODE, "tuning/legacy/env_transfer.py"), r"reward\s*=")}}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--agent", required=True, choices=("derp", "lstm_scratch", "dinos_t"))
    p.add_argument("--agent-variant", default="verbatim", choices=("verbatim", "fixed", "dense_fixed"))
    p.add_argument("--state-size", type=int, default=6)
    p.add_argument("--derp-history", type=int, default=1)
    p.add_argument("--transfer", action="store_true")
    a = p.parse_args(argv)
    os.chdir(CODE)
    with open(os.devnull, "w") as dn:
        so, sys.stdout = sys.stdout, dn
        try:
            d = describe(a.agent, a.agent_variant, a.state_size, a.derp_history, a.transfer)
        finally:
            sys.stdout = so
    print(json.dumps(d))


if __name__ == "__main__":
    main()
