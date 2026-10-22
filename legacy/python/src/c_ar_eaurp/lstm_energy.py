"""LSTM predictive energy harvesting -- AR-EAURP step 3.

Replaces the linear depletion of Lekha.pdf Eq. (8) with a solar/kinetic model,
and forecasts the energy each node will harvest over the next
``LSTM_HORIZON`` rounds. That forecast becomes a new DRL state feature and a
route-scoring term, so the agent can prefer relays that are *about to be*
energy-rich rather than only those that are rich now.

WHY THE BASELINES ARE NOT OPTIONAL
----------------------------------
An LSTM that beats nothing has proved nothing. The harvest signal here is a
diurnal sinusoid times an AR(1) cloud process, and a sinusoid is extremely
predictable -- a "same time yesterday" lookup already does well on it. So every
run reports three numbers:

    persistence     last observed harvest, held for the horizon
    seasonal naive  the same window exactly one day earlier
    LSTM            the learned model

If the LSTM does not beat both, the report says so. This is exactly the concern
raised in the Review-1 critique ("LSTM prediction is only as good as the traces
it is trained on"), so it is measured rather than asserted.
"""

import numpy as np

from ..common import config

try:  # pragma: no cover - depends on the runtime environment
    import torch
    import torch.nn as nn

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    TORCH_AVAILABLE = False

N_FEATURES = 4  # harvest, normalised energy, sin(phase), cos(phase)


def generate_harvest_traces(n_nodes, n_rounds, rng, day_length=None,
                            panel_fraction=None):
    """Simulate the solar/kinetic harvest process on its own.

    Used to build the LSTM's training set without running a full network
    simulation. Uses the same generative process as
    ``common.energy.SolarHarvesting`` so the model trains on the signal it will
    actually see.
    """
    day_length = config.HARVEST_DAY_LENGTH if day_length is None else float(day_length)
    panel_fraction = (
        config.HARVEST_PANEL_FRACTION if panel_fraction is None else float(panel_fraction)
    )

    has_panel = rng.random(n_nodes) < panel_fraction
    gains = rng.uniform(config.HARVEST_PEAK_MIN, config.HARVEST_PEAK_MAX, n_nodes)
    panel_gain = np.where(has_panel, gains, 0.0)

    cloud = np.ones(n_nodes)
    harvest = np.zeros((n_rounds, n_nodes))
    energy = np.full(n_nodes, config.INITIAL_ENERGY)
    energy_trace = np.zeros((n_rounds, n_nodes))

    for step in range(n_rounds):
        noise = rng.normal(0.0, config.HARVEST_CLOUD_SIGMA, n_nodes)
        cloud = (
            config.HARVEST_CLOUD_RHO * cloud
            + (1.0 - config.HARVEST_CLOUD_RHO) * 1.0
            + noise * (1.0 - config.HARVEST_CLOUD_RHO)
        )
        cloud = np.clip(cloud, 0.0, 1.5)

        irradiance = max(0.0, float(np.sin(2.0 * np.pi * step / day_length)))
        gain = np.clip(panel_gain * irradiance * cloud, 0.0, None)
        harvest[step] = gain

        drain = rng.uniform(config.IDLE_DRAIN_MIN, config.IDLE_DRAIN_MAX, n_nodes)
        energy = np.clip(energy + gain - drain, 0.0, config.MAX_ENERGY_CAP)
        energy_trace[step] = energy

    return harvest, energy_trace, panel_gain


def phase_features(rounds, day_length=None):
    """Time-of-day encoding, as sin/cos so midnight is not a discontinuity."""
    day_length = config.HARVEST_DAY_LENGTH if day_length is None else float(day_length)
    phase = 2.0 * np.pi * (np.asarray(rounds, dtype=float) / day_length)
    return np.sin(phase), np.cos(phase)


def build_dataset(harvest, energy_trace, input_len=None, horizon=None,
                  day_length=None):
    """Windows of past behaviour -> total harvest over the next ``horizon``."""
    input_len = config.LSTM_INPUT_LEN if input_len is None else int(input_len)
    horizon = config.LSTM_HORIZON if horizon is None else int(horizon)

    n_rounds, n_nodes = harvest.shape
    sin_phase, cos_phase = phase_features(np.arange(n_rounds), day_length)

    inputs, targets = [], []
    last_values = []
    seasonal = []
    day_length = config.HARVEST_DAY_LENGTH if day_length is None else float(day_length)
    day_steps = int(round(day_length))

    for start in range(n_rounds - input_len - horizon):
        stop = start + input_len
        window_harvest = harvest[start:stop, :]
        window_energy = energy_trace[start:stop, :] / config.MAX_ENERGY_CAP
        target = harvest[stop:stop + horizon, :].sum(axis=0)

        window = np.stack(
            [
                window_harvest,
                window_energy,
                np.repeat(sin_phase[start:stop, None], n_nodes, axis=1),
                np.repeat(cos_phase[start:stop, None], n_nodes, axis=1),
            ],
            axis=-1,
        )  # (input_len, n_nodes, N_FEATURES)

        inputs.append(np.transpose(window, (1, 0, 2)))  # (n_nodes, input_len, F)
        targets.append(target)
        last_values.append(window_harvest[-1, :] * horizon)

        # "Same window, one day ago" -- the seasonal-naive baseline.
        prior = stop - day_steps
        if prior >= 0:
            seasonal.append(harvest[prior:prior + horizon, :].sum(axis=0))
        else:
            seasonal.append(window_harvest[-1, :] * horizon)

    if not inputs:
        empty = np.zeros((0, input_len, N_FEATURES))
        return empty, np.zeros(0), np.zeros(0), np.zeros(0)

    X = np.concatenate(inputs, axis=0)
    y = np.concatenate(targets, axis=0)
    persistence = np.concatenate(last_values, axis=0)
    seasonal_naive = np.concatenate(seasonal, axis=0)
    return X, y, persistence, seasonal_naive


if TORCH_AVAILABLE:

    class _LstmRegressor(nn.Module):
        def __init__(self, n_features, hidden):
            super(_LstmRegressor, self).__init__()
            self.lstm = nn.LSTM(n_features, hidden, batch_first=True)
            self.head = nn.Linear(hidden, 1)

        def forward(self, x):
            output, _ = self.lstm(x)
            return self.head(output[:, -1, :]).squeeze(-1)


class EnergyHarvestPredictor(object):
    """Forecasts cumulative harvest over the next ``LSTM_HORIZON`` rounds."""

    def __init__(self, hidden=None, input_len=None, horizon=None, lr=None,
                 epochs=None, seed=0):
        self.hidden = config.LSTM_HIDDEN if hidden is None else int(hidden)
        self.input_len = config.LSTM_INPUT_LEN if input_len is None else int(input_len)
        self.horizon = config.LSTM_HORIZON if horizon is None else int(horizon)
        self.lr = config.LSTM_LR if lr is None else float(lr)
        self.epochs = config.LSTM_EPOCHS if epochs is None else int(epochs)
        self.seed = int(seed)

        self.model = None
        self.backend = "torch" if TORCH_AVAILABLE else "persistence-fallback"
        self.using_fallback = not TORCH_AVAILABLE
        self.trained = False
        self.history = []
        self.evaluation = {}
        self._y_scale = 1.0

    def fit(self, n_nodes=60, n_rounds=1200, seed=None, epochs=None,
            validation_split=0.25):
        """Train on freshly generated harvest traces."""
        rng = np.random.default_rng(self.seed if seed is None else int(seed))
        harvest, energy_trace, _ = generate_harvest_traces(n_nodes, n_rounds, rng)
        X, y, persistence, seasonal = build_dataset(
            harvest, energy_trace, self.input_len, self.horizon
        )
        if X.shape[0] < 64:
            self.using_fallback = True
            self.trained = True
            return self.summary()

        split = int((1.0 - validation_split) * X.shape[0])
        order = rng.permutation(X.shape[0])
        train_idx, test_idx = order[:split], order[split:]

        self._y_scale = float(np.abs(y[train_idx]).max()) or 1.0

        if TORCH_AVAILABLE:
            torch.manual_seed(self.seed)
            self.model = _LstmRegressor(N_FEATURES, self.hidden)
            optimiser = torch.optim.Adam(self.model.parameters(), lr=self.lr)
            loss_fn = torch.nn.MSELoss()

            X_train = torch.from_numpy(X[train_idx].astype(np.float32))
            y_train = torch.from_numpy((y[train_idx] / self._y_scale).astype(np.float32))

            epochs = self.epochs if epochs is None else int(epochs)
            batch = 256
            self.history = []
            for _ in range(epochs):
                permutation = torch.randperm(X_train.shape[0])
                epoch_loss = 0.0
                batches = 0
                for start in range(0, X_train.shape[0], batch):
                    index = permutation[start:start + batch]
                    prediction = self.model(X_train[index])
                    loss = loss_fn(prediction, y_train[index])
                    optimiser.zero_grad()
                    loss.backward()
                    optimiser.step()
                    epoch_loss += float(loss.item())
                    batches += 1
                self.history.append(epoch_loss / max(1, batches))
            self.trained = True

        self.evaluation = self.evaluate(
            X[test_idx], y[test_idx], persistence[test_idx], seasonal[test_idx]
        )
        return self.summary()

    def predict_batch(self, X):
        """Predicted cumulative harvest for a batch of windows."""
        X = np.asarray(X, dtype=np.float32)
        if X.size == 0:
            return np.zeros(0)
        if self.using_fallback or self.model is None:
            # Persistence: hold the last observed harvest for the horizon.
            return X[:, -1, 0] * self.horizon
        with torch.no_grad():
            output = self.model(torch.from_numpy(X)).numpy()
        return output * self._y_scale

    def evaluate(self, X, y, persistence, seasonal):
        """MAE / RMSE for the LSTM and both baselines."""
        prediction = self.predict_batch(X)

        def errors(pred):
            residual = np.asarray(pred, dtype=float) - np.asarray(y, dtype=float)
            return float(np.abs(residual).mean()), float(np.sqrt((residual ** 2).mean()))

        lstm_mae, lstm_rmse = errors(prediction)
        pers_mae, pers_rmse = errors(persistence)
        seas_mae, seas_rmse = errors(seasonal)

        best_baseline = min(pers_mae, seas_mae)
        # A margin, because in fallback mode the "model" *is* persistence and a
        # bit-level float difference must not be reported as beating it.
        margin = 1e-6 + 0.001 * max(pers_mae, seas_mae)
        return {
            "n_test": int(len(y)),
            "lstm_mae": lstm_mae,
            "lstm_rmse": lstm_rmse,
            "persistence_mae": pers_mae,
            "persistence_rmse": pers_rmse,
            "seasonal_naive_mae": seas_mae,
            "seasonal_naive_rmse": seas_rmse,
            "beats_persistence": bool(lstm_mae < pers_mae - margin),
            "beats_seasonal_naive": bool(lstm_mae < seas_mae - margin),
            "improvement_over_best_baseline": (
                float((best_baseline - lstm_mae) / best_baseline)
                if best_baseline > 0 else 0.0
            ),
        }

    # -- online use inside the simulation ---------------------------------

    def predicted_surplus(self, harvest_history, energy_history, round_idx):
        """Per-node forecast from live simulation history.

        ``harvest_history`` and ``energy_history`` are ``(T, n_nodes)`` arrays of
        the most recent rounds. Falls back to persistence until enough history
        has accumulated.
        """
        harvest_history = np.asarray(harvest_history, dtype=float)
        if harvest_history.ndim != 2 or harvest_history.shape[0] < self.input_len:
            if harvest_history.size == 0:
                return None
            return harvest_history[-1] * self.horizon

        window_harvest = harvest_history[-self.input_len:]
        window_energy = (
            np.asarray(energy_history, dtype=float)[-self.input_len:]
            / config.MAX_ENERGY_CAP
        )
        rounds = np.arange(round_idx - self.input_len + 1, round_idx + 1)
        sin_phase, cos_phase = phase_features(rounds)
        n_nodes = window_harvest.shape[1]

        window = np.stack(
            [
                window_harvest,
                window_energy,
                np.repeat(sin_phase[:, None], n_nodes, axis=1),
                np.repeat(cos_phase[:, None], n_nodes, axis=1),
            ],
            axis=-1,
        )
        X = np.transpose(window, (1, 0, 2))
        return self.predict_batch(X)

    def summary(self):
        row = {
            "lstm_backend": self.backend,
            "lstm_using_fallback": bool(self.using_fallback),
            "lstm_epochs_run": len(self.history),
            "lstm_final_loss": float(self.history[-1]) if self.history else None,
            "lstm_horizon": self.horizon,
        }
        row.update({"lstm_eval_" + k: v for k, v in self.evaluation.items()})
        return row
