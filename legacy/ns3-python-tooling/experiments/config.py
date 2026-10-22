"""Experiment budgets and sweep values in ns-3 physical units."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Profile:
    name: str
    duration: float
    warmup: float
    commission: float
    runs: int
    gan_epochs: int
    lstm_epochs: int
    lifetime: float

PROFILES = {
    "smoke": Profile("smoke", 12, 2, 100, 1, 2, 1, 40),
    "quick": Profile("quick", 120, 20, 120, 2, 60, 10, 900),
    "full": Profile("full", 400, 30, 240, 5, 120, 30, 1500),
}
SPEEDS = (1.0, 5.0, 10.0, 15.0, 20.0)
NODE_COUNTS = (60, 80, 100, 120, 150, 200)
MALICIOUS_FRACTIONS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)
ATTACKS = ("blackhole", "grayhole", "trust_poisoning")

def get_profile(name):
    return PROFILES[name]
