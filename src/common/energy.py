"""Energy models.

Two models are provided:

``LinearDepletion``
    Lekha.pdf Eq. (8): ``E(t+1) = E(t) - dE``, ``dE ~ U[0.05, 0.15]``. This is
    what both papers use and what the senior's notebook implements. Note that
    it is monotonically decreasing and completely independent of what the node
    actually does, which is one of the limitations the advancement targets.

``SolarHarvesting``
    The AR-EAURP replacement (docx step 3): ``E(t+1) = E(t) - dE + H(t)`` with
    a diurnal solar term modulated by an AR(1) cloud process, plus a small
    kinetic term proportional to node speed. Only a fraction of nodes carry a
    panel, so the DRL agent has something non-trivial to learn: route through
    the nodes that are *predicted* to be in surplus.
"""

import numpy as np

from . import config


def _kill_newly_dead(nodes, round_idx):
    """Mark nodes whose battery just ran out."""
    newly_dead = nodes.alive & (nodes.energy <= 0.0)
    if newly_dead.any():
        nodes.energy[newly_dead] = 0.0
        nodes.alive[newly_dead] = False
        nodes.death_round[newly_dead] = int(round_idx)
    return int(newly_dead.sum())


class EnergyModel(object):
    """Interface shared by every energy model."""

    name = "base"

    def reset(self, nodes, rng_channel):
        """Hook for per-run initialisation."""
        return None

    def step(self, nodes, round_idx, rng_channel):
        raise NotImplementedError

    def transmit_cost(self, size_bytes):
        return config.ENERGY_TX * (float(size_bytes) / 1024.0)

    def receive_cost(self, size_bytes):
        return config.ENERGY_RX * (float(size_bytes) / 1024.0)


class LinearDepletion(EnergyModel):
    """Lekha.pdf Eq. (8) -- constant random drain, no harvesting."""

    name = "linear"

    def __init__(self, drain_min=None, drain_max=None):
        self.drain_min = config.IDLE_DRAIN_MIN if drain_min is None else float(drain_min)
        self.drain_max = config.IDLE_DRAIN_MAX if drain_max is None else float(drain_max)
        if self.drain_max < self.drain_min:
            raise ValueError("drain_max must be >= drain_min")

    def step(self, nodes, round_idx, rng_channel):
        drain = rng_channel.uniform(self.drain_min, self.drain_max, nodes.n)
        nodes.energy[nodes.alive] -= drain[nodes.alive]
        nodes.harvest_last[:] = 0.0
        return _kill_newly_dead(nodes, round_idx)


class SolarHarvesting(EnergyModel):
    """AR-EAURP energy model with diurnal solar plus kinetic harvesting."""

    name = "solar"

    def __init__(self, drain_min=None, drain_max=None, day_length=None):
        self.drain_min = config.IDLE_DRAIN_MIN if drain_min is None else float(drain_min)
        self.drain_max = config.IDLE_DRAIN_MAX if drain_max is None else float(drain_max)
        self.day_length = (
            config.HARVEST_DAY_LENGTH if day_length is None else float(day_length)
        )

    def reset(self, nodes, rng_channel):
        """Assign heterogeneous panels; some nodes deliberately have none."""
        has_panel = rng_channel.random(nodes.n) < config.HARVEST_PANEL_FRACTION
        gains = rng_channel.uniform(
            config.HARVEST_PEAK_MIN, config.HARVEST_PEAK_MAX, nodes.n
        )
        nodes.panel_gain = np.where(has_panel, gains, 0.0)
        nodes.cloud = np.ones(nodes.n)
        nodes.harvest_last = np.zeros(nodes.n)
        return nodes.panel_gain

    def irradiance(self, round_idx):
        """Diurnal term in [0, 1]; zero for the half of the day that is night."""
        phase = 2.0 * np.pi * (float(round_idx) / self.day_length)
        return max(0.0, float(np.sin(phase)))

    def harvest(self, nodes, round_idx, rng_channel):
        """Energy harvested by each node this round."""
        # AR(1) cloud occlusion, shared shape across nodes but independent noise.
        noise = rng_channel.normal(0.0, config.HARVEST_CLOUD_SIGMA, nodes.n)
        nodes.cloud = config.HARVEST_CLOUD_RHO * nodes.cloud + (
            1.0 - config.HARVEST_CLOUD_RHO
        ) * 1.0 + noise * (1.0 - config.HARVEST_CLOUD_RHO)
        np.clip(nodes.cloud, 0.0, 1.5, out=nodes.cloud)

        solar = nodes.panel_gain * self.irradiance(round_idx) * nodes.cloud
        kinetic = config.KINETIC_GAIN * nodes.speed
        return np.clip(solar + kinetic, 0.0, None)

    def step(self, nodes, round_idx, rng_channel):
        drain = rng_channel.uniform(self.drain_min, self.drain_max, nodes.n)
        gain = self.harvest(nodes, round_idx, rng_channel)
        nodes.harvest_last = gain

        delta = gain - drain
        nodes.energy[nodes.alive] += delta[nodes.alive]
        np.clip(nodes.energy, None, config.MAX_ENERGY_CAP, out=nodes.energy)
        return _kill_newly_dead(nodes, round_idx)


def make_energy_model(name, **kwargs):
    """Factory used by the experiment scripts and the notebook."""
    key = str(name).lower()
    if key in ("linear", "lekha", "eq8"):
        return LinearDepletion(**kwargs)
    if key in ("solar", "harvest", "harvesting"):
        return SolarHarvesting(**kwargs)
    raise ValueError("unknown energy model {0!r}".format(name))
