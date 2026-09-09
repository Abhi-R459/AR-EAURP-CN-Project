"""Global configuration for the AR-EAURP Review-2 simulations.

Every constant here is traceable to one of the two source papers:

  base.pdf  -- EAURP, A. Chandra & A.S.N. Chakravarthy, Sustainable Computing 2025
  Lekha.pdf -- DRL-EAURP, Lekha S., VIT Vellore

Section / equation references are given inline so the review panel can check
each value against the paper it came from.
"""

from dataclasses import dataclass

# --------------------------------------------------------------------------
# Network geometry -- base.pdf 3.2 / Lekha.pdf Sec. IV-A
# --------------------------------------------------------------------------
AREA_SIZE = 1000.0          # square deployment region, 1000 x 1000
COMM_RANGE = 150.0          # link exists iff d_ij <= R   (Lekha Eq. 4)

# --------------------------------------------------------------------------
# Energy model -- base.pdf 3.5 / Lekha.pdf Eq. (8)
# --------------------------------------------------------------------------
INITIAL_ENERGY = 100.0
ENERGY_TX = 0.5             # per 1024-byte transmission
ENERGY_RX = 0.2             # per 1024-byte reception
IDLE_DRAIN_MIN = 0.04       # senior proposed-model drain band
IDLE_DRAIN_MAX = 0.12
IDLE_DRAIN_MIN_BASE = 0.05  # senior EAURP-base drain band (Lekha Eq. 8)
IDLE_DRAIN_MAX_BASE = 0.15
ENERGY_THRESHOLD_FRAC = 0.2  # base.pdf 3.5: threshold = 0.2 * initial energy
DEAD_FRACTION_STOP = 0.8     # stop when 80% of nodes are dead (Lekha Sec. IV-A-3)

# --------------------------------------------------------------------------
# Trust model -- base.pdf 3.7 / Lekha.pdf Eq. (19)-(21)
# --------------------------------------------------------------------------
TRUST_THRESHOLD = 0.6        # PFR < 0.6 => suspicious (base.pdf 3.7)
TRUST_SMOOTHING = 0.7        # Lekha Eq. 20: T <- 0.7*T + 0.3*PFR
MIN_OBSERVATIONS = 5         # Lekha Eq. 21: classify only once R_i > 5
INITIAL_TRUST = 1.0

# Predictive trust weights -- Lekha Eq. (26)
PREDICTIVE_WEIGHTS = (0.5, 0.3, 0.2)
TRUST_HISTORY_LEN = 3

# --------------------------------------------------------------------------
# Mobility
# --------------------------------------------------------------------------
# Both papers sweep 10,000-40,000 "m/s", which is not physically meaningful for
# a MANET. We keep those values so our curves line up with the published ones,
# and additionally expose a realistic sweep that is reported as an annex.
SPEEDS_PAPER = [10000, 15000, 20000, 25000, 30000, 35000, 40000]
SPEEDS_REALISTIC = [1.0, 5.0, 10.0, 15.0, 20.0]
MAX_SPEED = 40000.0          # v_max used in the mobility factor (Lekha Eq. 22)
MOVE_SCALE = 0.001           # displacement = speed * MOVE_SCALE per round

NODE_COUNTS = [60, 80, 100, 120, 150, 200]
DEFAULT_NODES = 100
DEFAULT_SPEED = 20000

# --------------------------------------------------------------------------
# Traffic
# --------------------------------------------------------------------------
PACKET_SIZE_MIN = 512
PACKET_SIZE_MAX = 1024
PACKETS_PER_ROUND = 4
# 40 concurrent flows, not 10. Watchdog trust only accumulates on nodes that
# actually relay traffic, so path diversity is what determines detection
# coverage: raising this from 10 to 40 lifts black-hole detection recall from
# 0.23 to 0.47 with no other change.
N_FLOWS = 40                 # persistent CBR flows (Track 2 default)
LARGE_PACKET_THRESHOLD = 700  # grayhole selective-forwarding boundary (bytes)

# --------------------------------------------------------------------------
# Delay model -- Lekha.pdf Eq. (12): D = D_base + H * D_hop
# --------------------------------------------------------------------------
BASE_DELAY_MIN = 20.0
BASE_DELAY_MAX = 50.0
HOP_DELAY_MIN = 4.0
HOP_DELAY_MAX = 10.0

# --------------------------------------------------------------------------
# Link reliability (Track 2 mechanistic channel)
# --------------------------------------------------------------------------
# CALIBRATION NOTE -- state this at the review. Neither source paper contains a
# PHY or link model: both compute one global success probability per packet and
# flip a coin (Lekha Eq. 7/24/28/35). Any per-hop reliability we use is
# therefore our own modelling assumption, not something inherited from the
# papers. These values were chosen so that a clean 100-node network lands at
# PDR ~0.85-0.91 across the speed sweep, i.e. the same regime the papers report,
# leaving headroom for attacks to be visible. Every conclusion in the report
# rests on *relative* comparisons under identical channel settings.
LINK_BASE_RELIABILITY = 0.995  # per-hop success at zero range utilisation
LINK_RANGE_PENALTY = 0.02      # subtracted at the edge of COMM_RANGE
LINK_MOBILITY_PENALTY = 0.03   # subtracted at MAX_SPEED
LINK_MIN_RELIABILITY = 0.90

# MEASURED PROPERTY OF THE PAPERS' OWN TOPOLOGY -- at their stated parameters
# (N=100, AREA=1000x1000, R=150) only ~90.7% of node pairs are mutually
# reachable; the mean degree is 6.1 and the giant component holds ~95% of nodes.
# At N=60 reachability collapses to ~39%. A routing protocol cannot deliver
# across a partition, so a "no route" floor is inherent to the papers'
# configuration and is reported as its own loss category.

# --------------------------------------------------------------------------
# Control plane -- base.pdf 3.6
# --------------------------------------------------------------------------
PT_NID_PERIOD = 10            # rounds between PT_NID neighbour reports
PT_GID_PERIOD = 25            # rounds between PT_GID consensus rounds
GID_CONSENSUS_FRACTION = 0.5  # "majority of nodes detect a node as malicious"
GID_MIN_ACCUSERS = 2

# --------------------------------------------------------------------------
# Reinforcement learning -- Lekha.pdf Eq. (3), (33)-(37)
# --------------------------------------------------------------------------
RL_ALPHA = 0.1
RL_GAMMA = 0.9
RL_EPSILON = 0.1
REWARD_SUCCESS = 1.0
REWARD_FAILURE = -1.0

# --------------------------------------------------------------------------
# AR-EAURP (C) -- Date_24_07_26.docx
# --------------------------------------------------------------------------
GAN_FEATURE_DIM = 8
GAN_LATENT_DIM = 8
GAN_HIDDEN = 32
GAN_EPOCHS = 300
GAN_BATCH = 64
GAN_LR = 2e-4
GAN_LABEL_SMOOTH = 0.9
GAN_THRESHOLD_PERCENTILE = 95.0
CONTESTED_TRUST_WEIGHT = 0.5   # docx: "downgrades its trust weight by 50%"
CONTESTED_TTL = 50             # rounds a node stays contested
DETECT_PERIOD = 25             # rounds between anomaly-detection passes
FEATURE_WINDOW = 50            # observation window for the feature vector

LSTM_HIDDEN = 32
LSTM_INPUT_LEN = 20
LSTM_HORIZON = 10              # docx: "predict energy for the next 10 rounds"
LSTM_EPOCHS = 40
LSTM_LR = 1e-3

# Solar / kinetic harvesting
HARVEST_DAY_LENGTH = 400.0     # rounds per simulated day
HARVEST_PANEL_FRACTION = 0.7   # fraction of nodes carrying a panel
HARVEST_PEAK_MIN = 0.05
HARVEST_PEAK_MAX = 0.16
HARVEST_CLOUD_RHO = 0.92       # AR(1) cloud-occlusion persistence
HARVEST_CLOUD_SIGMA = 0.12
KINETIC_GAIN = 2.0e-7          # per unit speed
MAX_ENERGY_CAP = 120.0         # battery cannot exceed this

# CMDP -- docx step 4
CMDP_PDR_FLOOR = 0.90
CMDP_WINDOW = 100              # rounds in the running PDR window
CMDP_PENALTY = 5.0
CMDP_LAMBDA_LR = 0.05
CMDP_LAMBDA_MAX = 20.0

# DQN
DQN_HIDDEN = 64
DQN_BUFFER = 5000
DQN_BATCH = 64
DQN_LR = 1e-3
DQN_TARGET_SYNC = 200
DQN_EPS_START = 0.30
DQN_EPS_END = 0.05
DQN_EPS_DECAY = 800

# Attack sweep -- docx step 5
MALICIOUS_FRACTIONS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
ATTACKS = ["blackhole", "grayhole", "trust_poisoning"]
# Tuned so the *observed* PFR lands near 0.84 -- i.e. an overall drop rate of
# ~15%, exactly the "dropping just 15% of packets to stay above the 0.6 trust
# threshold" attack the advancement doc describes. With sizes ~ U[512,1024]
# about 63% of packets are "large", so 0.25 * 0.63 = 0.158 overall loss.
GRAYHOLE_LARGE_DROP_P = 0.25  # drop prob. for packets >= LARGE_PACKET_THRESHOLD
SLANDER_HIGH = 1.0            # trust a slanderer reports for its colluders
SLANDER_LOW = 0.15            # trust a slanderer reports for honest victims


@dataclass(frozen=True)
class Profile:
    """Runtime budget. QUICK is for smoke tests, FULL for the review numbers."""

    name: str
    rounds: int
    runs: int
    packets_per_round: int
    gan_epochs: int
    lstm_epochs: int


# ROUND-BUDGET NOTE -- worth explaining at the review.
#
# The papers charge energy only to an idle drain (Lekha Eq. 8) and never to
# transmission, so their networks survive ~1250 rounds. Once per-hop TX/RX cost
# is actually modelled, a 100-node network under load drains at ~0.17 J/round,
# and base.pdf's own rule -- exclude any node below 20% of initial energy --
# starts removing relays from round ~200 and has emptied the network by ~800.
#
# We therefore run the performance sweeps over a window in which the network is
# genuinely operational, and measure network lifetime in its own long-running
# experiment. Both numbers are reported; conflating them is what lets the
# papers claim a ~1230-round lifetime alongside a 0.96 delivery ratio.
LIFETIME_ROUNDS = 1500       # dedicated lifetime experiment (E4)

QUICK = Profile(
    name="quick",
    rounds=200,
    runs=2,
    packets_per_round=4,
    gan_epochs=60,
    lstm_epochs=10,
)

FULL = Profile(
    name="full",
    rounds=400,
    runs=5,
    packets_per_round=4,
    gan_epochs=300,
    lstm_epochs=40,
)

PROFILES = {"quick": QUICK, "full": FULL}


def get_profile(name):
    """Look up a runtime profile by name."""
    key = str(name).lower()
    if key not in PROFILES:
        raise ValueError(
            "unknown profile {0!r}; choose from {1}".format(name, sorted(PROFILES))
        )
    return PROFILES[key]


def energy_threshold():
    """base.pdf 3.5 -- nodes below 20% of initial energy are excluded."""
    return ENERGY_THRESHOLD_FRAC * INITIAL_ENERGY
