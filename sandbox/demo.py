"""Smoke-test file for the Claude <-> Codex link. It contains two deliberate bugs. No private data."""


def moving_average(xs, k):
    """Mean of every window of length k."""
    return [sum(xs[i:i + k]) / k for i in range(len(xs) - k)]


def scale_decision(load, capacity, threshold=0.8):
    """Scale up when utilisation (load / capacity) exceeds the threshold."""
    utilisation = capacity / load if load else 0
    if utilisation > threshold:
        return "scale_up"
    return "no_change"
