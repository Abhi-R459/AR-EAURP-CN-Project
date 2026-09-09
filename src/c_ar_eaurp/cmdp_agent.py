"""Constrained-MDP routing agent -- AR-EAURP step 4.

The doc asks for a hard constraint: PDR must stay above 90% even when the
adversary controls 30% of the nodes, with a large negative reward on violation.
Implemented as a Lagrangian CMDP, which is the standard way to turn "hard
constraint" into something a policy-gradient-free learner can actually optimise:

    r = +/-1  -  w_e * energy_cost  -  lambda * max(0, 0.90 - PDR_window) * C
    lambda <- clip(lambda + eta * (0.90 - PDR_window), 0, lambda_max)

``lambda`` rises while the constraint is violated, so the penalty grows until
the policy either satisfies the floor or saturates. That saturation is itself
the result worth reporting: the Review-1 critique flags the 90% floor as
possibly infeasible under sustained attack, and a lambda pinned at its ceiling
with the constraint still violated is direct evidence of exactly that. The
violation rate and the lambda trajectory are both logged.

STATE (extends Lekha.pdf Eq. 29 from three dimensions to six):

    T_robust          mean trust after the GAN's contested-node down-weighting
    E                 mean normalised residual energy
    M                 mean mobility factor
    E_pred_surplus    mean LSTM-predicted harvest over the next 10 rounds
    contested_ratio   fraction of nodes currently flagged by the detector
    pdr_window        running delivery ratio -- the constraint signal

ACTIONS (answering the Review-1 critique that a binary action space is coarse):

    0  route on trust
    1  route on predicted energy surplus
    2  route on the balanced EAURP R_Score
    3  route on a diversified, node-disjoint path

A two-action mode is kept for direct parity with the base paper.
"""

import numpy as np

from ..common import config

try:  # pragma: no cover - depends on the runtime environment
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    TORCH_AVAILABLE = False

# One gradient step per packet is wasteful and, over a 90-configuration attack
# sweep, is the single biggest cost in the whole evaluation: 400 rounds x 4
# packets x 5 runs x 90 configs is ~720k backward passes. Training every Nth
# transition keeps the same learning signal (every transition still enters the
# replay buffer) at a quarter of the cost.
TRAIN_EVERY = 4

STATE_DIM = 6
ACTION_TRUST = 0
ACTION_ENERGY = 1
ACTION_BALANCED = 2
ACTION_DIVERSE = 3
ACTION_NAMES = ("trust", "energy_surplus", "balanced", "diversified")

ENERGY_COST_WEIGHT = 0.05


if TORCH_AVAILABLE:

    class _QNetwork(nn.Module):
        def __init__(self, state_dim, hidden, n_actions):
            super(_QNetwork, self).__init__()
            self.net = nn.Sequential(
                nn.Linear(state_dim, hidden),
                nn.ReLU(),
                nn.Linear(hidden, hidden),
                nn.ReLU(),
                nn.Linear(hidden, n_actions),
            )

        def forward(self, x):
            return self.net(x)


class ReplayBuffer(object):
    """Fixed-capacity circular buffer of transitions."""

    def __init__(self, capacity, state_dim):
        self.capacity = int(capacity)
        self.states = np.zeros((self.capacity, state_dim), dtype=np.float32)
        self.actions = np.zeros(self.capacity, dtype=np.int64)
        self.rewards = np.zeros(self.capacity, dtype=np.float32)
        self.next_states = np.zeros((self.capacity, state_dim), dtype=np.float32)
        self.size = 0
        self.cursor = 0

    def add(self, state, action, reward, next_state):
        index = self.cursor
        self.states[index] = state
        self.actions[index] = action
        self.rewards[index] = reward
        self.next_states[index] = next_state
        self.cursor = (self.cursor + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size, rng):
        count = min(int(batch_size), self.size)
        index = rng.integers(0, self.size, count)
        return (
            self.states[index],
            self.actions[index],
            self.rewards[index],
            self.next_states[index],
        )


class CmdpRoutingAgent(object):
    """DQN with a Lagrangian PDR constraint; tabular fallback without torch."""

    def __init__(self, n_actions=4, hidden=None, lr=None, gamma=None,
                 buffer_size=None, batch_size=None, target_sync=None,
                 pdr_floor=None, seed=0):
        self.n_actions = int(n_actions)
        self.hidden = config.DQN_HIDDEN if hidden is None else int(hidden)
        self.lr = config.DQN_LR if lr is None else float(lr)
        self.gamma = config.RL_GAMMA if gamma is None else float(gamma)
        self.batch_size = config.DQN_BATCH if batch_size is None else int(batch_size)
        self.target_sync = (
            config.DQN_TARGET_SYNC if target_sync is None else int(target_sync)
        )
        self.pdr_floor = (
            config.CMDP_PDR_FLOOR if pdr_floor is None else float(pdr_floor)
        )
        self.seed = int(seed)

        self.backend = "dqn" if TORCH_AVAILABLE else "tabular-fallback"
        self.using_fallback = not TORCH_AVAILABLE

        self.buffer = ReplayBuffer(
            config.DQN_BUFFER if buffer_size is None else int(buffer_size), STATE_DIM
        )
        self.online = None
        self.target = None
        self.optimiser = None
        self._table = {}

        self.steps = 0
        self.train_steps = 0
        self._since_train = 0
        self.epsilon = config.DQN_EPS_START
        self.lam = 0.0
        self.lambda_trace = []
        self.action_counts = np.zeros(self.n_actions, dtype=np.int64)
        self.losses = []
        self.constraint_checks = 0
        self.constraint_violations = 0

        if TORCH_AVAILABLE:
            torch.manual_seed(self.seed)
            self.online = _QNetwork(STATE_DIM, self.hidden, self.n_actions)
            self.target = _QNetwork(STATE_DIM, self.hidden, self.n_actions)
            self.target.load_state_dict(self.online.state_dict())
            self.optimiser = torch.optim.Adam(self.online.parameters(), lr=self.lr)

    # -- policy ------------------------------------------------------------

    def _discretise(self, state):
        """Tabular fallback key: one decimal per dimension."""
        return tuple(round(float(v), 1) for v in state)

    def q_values(self, state):
        if self.using_fallback or self.online is None:
            return np.asarray(
                self._table.setdefault(self._discretise(state),
                                       [0.0] * self.n_actions),
                dtype=float,
            )
        with torch.no_grad():
            tensor = torch.from_numpy(np.asarray(state, dtype=np.float32)[None, :])
            return self.online(tensor).numpy().ravel()

    def act(self, state, rng):
        """Epsilon-greedy with a linear decay on epsilon."""
        self.steps += 1
        self.epsilon = max(
            config.DQN_EPS_END,
            config.DQN_EPS_START
            - (config.DQN_EPS_START - config.DQN_EPS_END)
            * self.steps / float(config.DQN_EPS_DECAY),
        )
        if rng.random() < self.epsilon:
            action = int(rng.integers(0, self.n_actions))
        else:
            action = int(np.argmax(self.q_values(state)))
        self.action_counts[action] += 1
        return action

    # -- CMDP reward -------------------------------------------------------

    def shaped_reward(self, delivered, energy_cost, pdr_window):
        """Eq. (37) plus the energy term and the Lagrangian constraint penalty."""
        base = config.REWARD_SUCCESS if delivered else config.REWARD_FAILURE
        violation = max(0.0, self.pdr_floor - float(pdr_window))

        self.constraint_checks += 1
        if violation > 0.0:
            self.constraint_violations += 1

        penalty = self.lam * violation * config.CMDP_PENALTY
        return float(base - ENERGY_COST_WEIGHT * float(energy_cost) - penalty), violation

    def update_lambda(self, pdr_window):
        """Dual ascent on the constraint multiplier."""
        gap = self.pdr_floor - float(pdr_window)
        self.lam = float(
            np.clip(self.lam + config.CMDP_LAMBDA_LR * gap, 0.0, config.CMDP_LAMBDA_MAX)
        )
        self.lambda_trace.append(self.lam)
        return self.lam

    # -- learning ----------------------------------------------------------

    def observe(self, state, action, reward, next_state, rng):
        if self.using_fallback or self.online is None:
            key = self._discretise(state)
            next_key = self._discretise(next_state)
            values = self._table.setdefault(key, [0.0] * self.n_actions)
            next_values = self._table.setdefault(next_key, [0.0] * self.n_actions)
            values[action] += config.RL_ALPHA * (
                reward + self.gamma * max(next_values) - values[action]
            )
            self.train_steps += 1
            return

        self.buffer.add(state, action, reward, next_state)
        if self.buffer.size < max(self.batch_size, 64):
            return

        # Every transition is stored; only every TRAIN_EVERY-th one triggers a
        # gradient step. See the note on TRAIN_EVERY above.
        self._since_train += 1
        if self._since_train < TRAIN_EVERY:
            return
        self._since_train = 0

        states, actions, rewards, next_states = self.buffer.sample(
            self.batch_size, rng
        )
        states_t = torch.from_numpy(states)
        actions_t = torch.from_numpy(actions)
        rewards_t = torch.from_numpy(rewards)
        next_states_t = torch.from_numpy(next_states)

        q_selected = self.online(states_t).gather(1, actions_t[:, None]).squeeze(1)
        with torch.no_grad():
            target_q = rewards_t + self.gamma * self.target(next_states_t).max(dim=1)[0]

        loss = F.mse_loss(q_selected, target_q)
        self.optimiser.zero_grad()
        loss.backward()
        self.optimiser.step()

        self.losses.append(float(loss.item()))
        self.train_steps += 1
        if self.train_steps % self.target_sync == 0:
            self.target.load_state_dict(self.online.state_dict())

    # -- reporting ---------------------------------------------------------

    def summary(self):
        total = int(self.action_counts.sum()) or 1
        row = {
            "cmdp_backend": self.backend,
            "cmdp_using_fallback": bool(self.using_fallback),
            "cmdp_lambda_final": float(self.lam),
            "cmdp_lambda_max_seen": (
                float(max(self.lambda_trace)) if self.lambda_trace else 0.0
            ),
            "cmdp_lambda_saturated": bool(
                self.lambda_trace and max(self.lambda_trace) >= config.CMDP_LAMBDA_MAX - 1e-6
            ),
            "cmdp_constraint_checks": self.constraint_checks,
            "cmdp_constraint_violations": self.constraint_violations,
            "cmdp_violation_rate": (
                self.constraint_violations / float(self.constraint_checks)
                if self.constraint_checks else 0.0
            ),
            "dqn_train_steps": self.train_steps,
            "dqn_final_loss": float(self.losses[-1]) if self.losses else None,
            "dqn_epsilon_final": float(self.epsilon),
        }
        for index, name in enumerate(ACTION_NAMES[: self.n_actions]):
            row["action_share_" + name] = self.action_counts[index] / float(total)
        return row
