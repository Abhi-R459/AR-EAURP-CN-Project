"""AR-EAURP -- the advancement, assembled (docx step 5).

Built on the senior's DRL-EAURP: the Q-learning routing agent is kept and
extended, rather than replaced.

    base paper (B)          AR-EAURP (C)
    ----------------------  -----------------------------------------------
    trust = scalar PFR      trust down-weighted 50% for GAN-contested nodes
    state <T, E, M>         + predicted surplus, contested ratio, PDR window
    2 actions (+0.08/+0.02) 4 real route strategies
    reward +/-1             + energy term + Lagrangian PDR>=0.90 constraint
    linear energy drain     solar/kinetic harvesting with a 10-round forecast

TRAIN/TEST SEPARATION. The GAN is trained during a separate *clean*
commissioning run with no adversaries present, then frozen. It never sees an
attack before being evaluated on one. This matters: a detector tuned on the
attacks it is then scored against proves nothing.

DEFENCE ORDERING. A black-hole lies in its route reply, advertising a perfect
score. Lowering its measured trust therefore does nothing on its own -- the lie
overwrites it. So the contested down-weight is applied *after* the advertised
score, which is the only ordering in which the defence actually bites.
"""

import numpy as np

from ..common import config
from ..common.simulator import RoutingPolicy, SimParams, Simulation
from ..routing import aodv
from . import cmdp_agent as cmdp
from .gan_detector import GanAnomalyDetector
from .lstm_energy import EnergyHarvestPredictor
from .threat_model import BehaviourFeatureExtractor, aggregate_by_subject


class FeatureCollectorPolicy(RoutingPolicy):
    """Drives the clean commissioning run that produces the GAN's training set."""

    name = "collector"

    def __init__(self, detect_period=None):
        self.detect_period = (
            config.DETECT_PERIOD if detect_period is None else int(detect_period)
        )
        self.extractor = None
        self.windows = []

    def reset(self, sim):
        self.extractor = BehaviourFeatureExtractor(sim.nodes.n)
        self.windows = []
        sim.refresh_scores()

    def on_round_end(self, sim, round_idx):
        if round_idx > 0 and round_idx % self.detect_period == 0:
            features, _, _ = self.extractor.extract(sim.nodes)
            if features.shape[0]:
                self.windows.append(features)

    def collected(self):
        if not self.windows:
            return np.zeros((0, config.GAN_FEATURE_DIM))
        return np.concatenate(self.windows, axis=0)


def collect_clean_features(n_nodes=100, speed=20000, rounds=400, seed=9001,
                           energy_model="linear"):
    """Run an adversary-free simulation and return its behaviour windows."""
    policy = FeatureCollectorPolicy()
    params = SimParams(
        n_nodes=n_nodes, speed=speed, rounds=rounds, seed=seed,
        attack="none", malicious_fraction=0.0, energy_model=energy_model,
    )
    Simulation(policy, params).run()
    return policy.collected()


def collect_labelled_features(n_nodes=100, speed=20000, rounds=400, seed=9002,
                              attack="grayhole", malicious_fraction=0.3):
    """A held-out attacked run, used only to *measure* detector quality."""
    policy = FeatureCollectorPolicy()
    params = SimParams(
        n_nodes=n_nodes, speed=speed, rounds=rounds, seed=seed,
        attack=attack, malicious_fraction=malicious_fraction,
    )
    simulation = Simulation(policy, params)
    labels = []
    windows = []

    extractor = BehaviourFeatureExtractor(n_nodes)
    policy.extractor = extractor

    class _Labelling(FeatureCollectorPolicy):
        def on_round_end(self, inner_sim, round_idx):
            if round_idx > 0 and round_idx % self.detect_period == 0:
                features, _, subjects = self.extractor.extract(inner_sim.nodes)
                if features.shape[0]:
                    windows.append(features)
                    labels.append(inner_sim.nodes.malicious_mask()[subjects])

    simulation.policy = _Labelling()
    simulation.run()

    if not windows:
        return np.zeros((0, config.GAN_FEATURE_DIM)), np.zeros(0, dtype=bool)
    return np.concatenate(windows, axis=0), np.concatenate(labels, axis=0)


class ArEaurpPolicy(RoutingPolicy):
    """AR-EAURP: GAN-hardened trust + LSTM energy foresight + CMDP routing."""

    name = "C:AR-EAURP"

    def __init__(self, detector=None, predictor=None, agent=None,
                 use_gan=True, use_lstm=True, use_cmdp=True,
                 detect_period=None, n_actions=4):
        self.use_gan = bool(use_gan)
        self.use_lstm = bool(use_lstm)
        self.use_cmdp = bool(use_cmdp)
        self.detect_period = (
            config.DETECT_PERIOD if detect_period is None else int(detect_period)
        )

        self.detector = detector
        self.predictor = predictor
        self.agent = agent if agent is not None else cmdp.CmdpRoutingAgent(
            n_actions=int(n_actions)
        )

        self.extractor = None
        self.caches = {}
        self._pending = None
        self._surplus = None
        self._harvest_history = []
        self._energy_history = []
        self.contested_events = 0
        self.detection_passes = 0

    # -- setup -------------------------------------------------------------

    def pretrain(self, n_nodes=100, speed=20000, rounds=400, seed=9001,
                 gan_epochs=None, lstm_epochs=None, validate=True,
                 energy_model="linear", verbose=True):
        """Commissioning phase: train the detector and the forecaster.

        Both are trained on data that contains no attack, then frozen.
        """
        summary = {}

        if self.use_gan and self.detector is None:
            clean = collect_clean_features(
                n_nodes=n_nodes, speed=speed, rounds=rounds, seed=seed,
                energy_model=energy_model,
            )
            validation_features, validation_labels = (None, None)
            if validate:
                validation_features, validation_labels = collect_labelled_features(
                    n_nodes=n_nodes, speed=speed, rounds=rounds, seed=seed + 1,
                    attack="grayhole", malicious_fraction=0.3,
                )
            self.detector = GanAnomalyDetector(seed=seed)
            summary.update(
                self.detector.fit(
                    clean,
                    validation_features=validation_features,
                    validation_labels=validation_labels,
                    epochs=gan_epochs,
                )
            )
            summary["gan_clean_windows"] = int(clean.shape[0])
            if verbose:
                print("  [C] GAN trained on {0} clean windows; backend={1}; "
                      "val AUC={2}".format(
                          clean.shape[0], self.detector.backend,
                          summary.get("gan_val_auc")))

        if self.use_lstm and self.predictor is None:
            self.predictor = EnergyHarvestPredictor(seed=seed)
            summary.update(
                self.predictor.fit(n_nodes=60, n_rounds=1200, epochs=lstm_epochs)
            )
            if verbose:
                evaluation = self.predictor.evaluation
                print("  [C] LSTM backend={0}; MAE {1:.5f} vs persistence "
                      "{2:.5f} / seasonal {3:.5f}".format(
                          self.predictor.backend,
                          evaluation.get("lstm_mae", float("nan")),
                          evaluation.get("persistence_mae", float("nan")),
                          evaluation.get("seasonal_naive_mae", float("nan"))))
        return summary

    # -- harness hooks -----------------------------------------------------

    def reset(self, sim):
        self.extractor = BehaviourFeatureExtractor(sim.nodes.n)
        self.caches = {
            action: aodv.RouteCache() for action in range(self.agent.n_actions)
        }
        self._pending = None
        self._surplus = None
        self._harvest_history = []
        self._energy_history = []
        self.contested_events = 0
        self.detection_passes = 0
        self._refresh(sim)

    def robust_trust(self, sim):
        """Mean observed trust per node, before the contested down-weight."""
        return sim.nodes.network_trust()

    def _score_vectors(self, sim):
        """Three score vectors: trust-led, surplus-led and balanced."""
        nodes = sim.nodes
        trust = self.robust_trust(sim)
        energy = nodes.normalised_energy()

        surplus = energy
        if self.use_lstm and self._surplus is not None:
            span = float(np.ptp(self._surplus))
            if span > 1e-9:
                normalised = (self._surplus - self._surplus.min()) / span
            else:
                normalised = np.zeros_like(self._surplus)
            # Blend present energy with forecast headroom: a node that is low
            # now but about to recharge is a reasonable relay, one that is low
            # now and staying low is not.
            surplus = np.clip(0.5 * energy + 0.5 * normalised, 0.0, 1.0)

        vectors = {
            cmdp.ACTION_TRUST: aodv.route_scores(nodes, trust=trust, energy=energy * 0.0 + 1.0),
            cmdp.ACTION_ENERGY: aodv.route_scores(nodes, trust=trust, energy=surplus),
            cmdp.ACTION_BALANCED: aodv.route_scores(nodes, trust=trust, energy=energy),
        }
        vectors[cmdp.ACTION_DIVERSE] = vectors[cmdp.ACTION_BALANCED]

        # The contested down-weight is applied *after* route_scores, so that it
        # also bites on a black-hole's advertised (lied) score. Applying it
        # before would be overwritten by the lie and achieve nothing.
        if self.use_gan:
            contested = sim.nodes.contested
            if contested.any():
                for key in vectors:
                    vectors[key] = vectors[key].copy()
                    vectors[key][contested] *= config.CONTESTED_TRUST_WEIGHT
        return vectors

    def _refresh(self, sim):
        self._vectors = self._score_vectors(sim)
        sim.scores = self._vectors[cmdp.ACTION_BALANCED]

    def state_of(self, sim):
        """The six-dimensional CMDP state."""
        nodes = sim.nodes
        alive = nodes.alive
        if not alive.any():
            return np.zeros(cmdp.STATE_DIM, dtype=np.float32)

        trust = self.robust_trust(sim)
        if self.use_gan and nodes.contested.any():
            trust = trust.copy()
            trust[nodes.contested] *= config.CONTESTED_TRUST_WEIGHT

        surplus = 0.0
        if self.use_lstm and self._surplus is not None:
            surplus = float(np.clip(self._surplus[alive].mean() * 10.0, 0.0, 1.0))

        return np.array(
            [
                float(trust[alive].mean()),
                float(nodes.normalised_energy()[alive].mean()),
                float(nodes.mobility_factor()[alive].mean()),
                surplus,
                float(nodes.contested.mean()),
                float(sim.metrics.window_pdr()),
            ],
            dtype=np.float32,
        )

    def on_round_start(self, sim, round_idx):
        nodes = sim.nodes

        # Expire contested flags whose time-to-live has run out.
        if nodes.contested.any():
            expired = nodes.contested & (nodes.contested_until <= round_idx)
            if expired.any():
                nodes.contested[expired] = False

        # Track harvest/energy history for the forecaster.
        if self.use_lstm:
            self._harvest_history.append(nodes.harvest_last.copy())
            self._energy_history.append(nodes.energy.copy())
            keep = max(self.predictor.input_len if self.predictor else 20, 20)
            if len(self._harvest_history) > keep:
                self._harvest_history.pop(0)
                self._energy_history.pop(0)

        if round_idx > 0 and round_idx % self.detect_period == 0:
            self._detection_pass(sim, round_idx)
            self._forecast(sim, round_idx)
            self._refresh(sim)

    def _detection_pass(self, sim, round_idx):
        """Score recent behaviour and mark deviating nodes contested."""
        if not self.use_gan or self.detector is None or self.extractor is None:
            return
        features, observers, subjects = self.extractor.extract(sim.nodes)
        if features.shape[0] == 0:
            return

        self.detection_passes += 1
        flags, scores = self.detector.flag(features)
        per_node = aggregate_by_subject(
            scores.astype(float), subjects, sim.nodes.n, reduce="mean"
        )
        sim.nodes.anomaly_score = per_node

        # A node is contested when its *mean* score across observers clears the
        # threshold. Using the mean rather than the max is deliberate: it stops
        # a lone slanderer getting an honest node flagged by itself.
        contested = per_node > self.detector.threshold
        newly = contested & (~sim.nodes.contested)
        self.contested_events += int(newly.sum())

        sim.nodes.contested[contested] = True
        sim.nodes.contested_until[contested] = int(round_idx) + config.CONTESTED_TTL

    def _forecast(self, sim, round_idx):
        if not self.use_lstm or self.predictor is None:
            return
        if len(self._harvest_history) < 2:
            return
        prediction = self.predictor.predicted_surplus(
            np.asarray(self._harvest_history),
            np.asarray(self._energy_history),
            round_idx,
        )
        if prediction is not None:
            self._surplus = np.asarray(prediction, dtype=float)

    def select_route(self, sim, packet):
        state = self.state_of(sim)
        action = self.agent.act(state, sim.seeds.policy)

        scores = self._vectors.get(action, sim.scores)
        cache = self.caches.get(action)

        path = cache.get(sim.nodes, packet.src, packet.dst) if cache else None
        if path is None:
            if action == cmdp.ACTION_DIVERSE:
                primary = aodv.find_route(
                    sim.nodes, packet.src, packet.dst, scores, mode=aodv.MODE_EAURP
                )
                path = aodv.find_diverse_route(
                    sim.nodes, packet.src, packet.dst, scores, primary=primary
                )
            else:
                path = aodv.find_route(
                    sim.nodes, packet.src, packet.dst, scores, mode=aodv.MODE_EAURP
                )
            sim.metrics.record_discovery(path is not None)
            if path is not None and cache:
                cache.put(packet.src, packet.dst, path)

        self._pending = (state, action)
        return path

    def on_result(self, sim, packet, delivered, path, hops, reason):
        if self._pending is None:
            return
        state, action = self._pending

        energy_cost = float(hops) * (config.ENERGY_TX + config.ENERGY_RX)
        pdr_window = sim.metrics.window_pdr()

        if self.use_cmdp:
            reward, violation = self.agent.shaped_reward(
                delivered, energy_cost, pdr_window
            )
            sim.metrics.record_cmdp_check(violation <= 0.0)
        else:
            reward = config.REWARD_SUCCESS if delivered else config.REWARD_FAILURE

        next_state = self.state_of(sim)
        self.agent.observe(state, action, reward, next_state, sim.seeds.policy)
        self._pending = None

    def on_round_end(self, sim, round_idx):
        if self.use_cmdp and round_idx % 10 == 0:
            self.agent.update_lambda(sim.metrics.window_pdr())

    def detected_mask(self, sim):
        """C flags a node either by GAN contest or by EAURP revocation."""
        return sim.nodes.contested | sim.nodes.revoked

    def extra_metrics(self, sim):
        row = {
            "c_use_gan": self.use_gan,
            "c_use_lstm": self.use_lstm,
            "c_use_cmdp": self.use_cmdp,
            "c_contested_events": self.contested_events,
            "c_detection_passes": self.detection_passes,
            "c_contested_final": int(sim.nodes.contested.sum()),
        }
        row.update(self.agent.summary())
        if self.detector is not None:
            row.update(self.detector.summary())
        if self.predictor is not None:
            row.update(self.predictor.summary())
        # feature_names is a list; drop it from the CSV row.
        row.pop("feature_names", None)
        return row
