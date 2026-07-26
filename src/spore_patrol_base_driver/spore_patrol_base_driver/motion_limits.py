"""Pure-Python helpers for chassis command limits."""


def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp value to the inclusive interval [lower, upper]."""

    return max(lower, min(upper, value))


def move_toward(current: float, target: float, maximum_delta: float) -> float:
    """Move current toward target without overshooting."""

    if maximum_delta < 0.0:
        raise ValueError("maximum_delta must be non-negative")
    return current + clamp(target - current, -maximum_delta, maximum_delta)
