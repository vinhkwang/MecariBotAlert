import random


def apply_jitter(base_delay_seconds: float, jitter_ratio: float, rng: random.Random) -> float:
    if base_delay_seconds < 0:
        raise ValueError(f"base_delay_seconds must not be negative: {base_delay_seconds}")
    if not 0 <= jitter_ratio <= 1:
        raise ValueError(f"jitter_ratio must be within [0, 1]: {jitter_ratio}")
    spread_seconds = base_delay_seconds * jitter_ratio
    return rng.uniform(base_delay_seconds - spread_seconds, base_delay_seconds + spread_seconds)
