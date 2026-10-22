"""Deterministic, stream-separated random number generation.

The whole point of this module: when we compare protocol A against B against C
we must be sure that any difference in the numbers comes from the *protocol*
and not from the protocols having consumed random numbers in a different order
and therefore having been handed a different world.

We solve that by giving each concern (topology, mobility, traffic, channel,
adversary, policy) its own independent generator, spawned from one master seed
via ``numpy.random.SeedSequence``. A protocol that draws more policy randomness
than another cannot shift the node layout, the mobility trace, the traffic
pattern or the adversary placement by even one bit.
"""

from dataclasses import dataclass

import numpy as np

# Order matters: spawned children are positional, so never reorder this list
# without regenerating every stored result.
STREAM_NAMES = (
    "topology",
    "mobility",
    "traffic",
    "channel",
    "adversary",
    "policy",
)


@dataclass
class SeedBundle:
    """One independent ``numpy`` generator per simulation concern."""

    master: int
    topology: np.random.Generator
    mobility: np.random.Generator
    traffic: np.random.Generator
    channel: np.random.Generator
    adversary: np.random.Generator
    policy: np.random.Generator

    def describe(self):
        return "SeedBundle(master={0})".format(self.master)


def make_seed_bundle(master_seed):
    """Build a :class:`SeedBundle` from a single integer master seed."""
    master_seed = int(master_seed)
    sequence = np.random.SeedSequence(master_seed)
    children = sequence.spawn(len(STREAM_NAMES))
    generators = {
        name: np.random.default_rng(child)
        for name, child in zip(STREAM_NAMES, children)
    }
    return SeedBundle(master=master_seed, **generators)


def run_seed(base_seed, run_index):
    """Derive a distinct master seed for run ``run_index`` of an experiment.

    Deliberately arithmetic rather than hashed so that the seed used for any
    reported number can be reconstructed by hand during the review.
    """
    return int(base_seed) + 1000 * int(run_index)
