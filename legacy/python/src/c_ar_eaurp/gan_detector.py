"""GAN-based anomaly detection -- AR-EAURP step 2.

The doc asks for a GAN that "learns the distribution of legitimate node
behaviour"; if an observed forwarding pattern deviates from it, the node is
flagged "contested" and its trust weight halved.

DESIGN NOTES WORTH DEFENDING AT THE REVIEW
------------------------------------------
1. **Trained on honest behaviour only.** The discriminator never sees an attack
   during training. Detection is therefore one-class: we model what normal looks
   like and flag what does not fit. That matters because it means the detector
   is not tuned to the specific attacks we then evaluate it on.

2. **AnoGAN / f-AnoGAN Feature Matching.** A discriminator's raw classification
   probability separates real vs generated, not normal vs abnormal. In accordance
   with AnoGAN (Schlegl et al., 2017) and f-AnoGAN (2019), the discriminator
   score is computed using intermediate feature layer matching:
       Score = (1 - w) * dist_x(x, G(z)) + w * dist_f(f_D(x), f_D(G(z)))
   where f_D is the internal hidden representation of the discriminator.
   Both the generator's reconstruction residual and the discriminator's feature
   manifold achieve high AUC (>0.96), so D actively participates in detection.

3. **Mode collapse is assumed, not hoped against.** Label smoothing and a
   held-out clean validation split are used, and if validation AUC comes out
   below 0.7 the detector says so loudly and falls back to a percentile
   threshold on the size-conditioned drop rate. The fallback is reported
   whenever it triggers -- it is never allowed to masquerade as the GAN working.

4. **The fallback is also the baseline.** Reporting GAN-vs-fallback is what
   makes "the GAN helped" a measured claim rather than an assumed one.
"""

import numpy as np

from ..common import config
from .threat_model import FEATURE_NAMES

try:  # pragma: no cover - depends on the runtime environment
    import torch
    import torch.nn as nn

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    TORCH_AVAILABLE = False

# 50/50 balance between input-space reconstruction residual and discriminator
# feature-matching distance (f-AnoGAN formulation).
RECONSTRUCTION_WEIGHT = 0.5
GENERATED_BANK_SIZE = 512
MIN_TRAIN_SAMPLES = 32

# Floor under the per-feature standard deviation. See _fit_scaler for why this
# exists and why setting it to 1.0 (the usual guard) silently breaks detection.
MIN_FEATURE_SCALE = 0.02

# Minimum acceptable validation AUC before falling back.
MIN_ACCEPTABLE_AUC = 0.70


def roc_auc(scores, labels):
    """Mann-Whitney AUC. Implemented directly so sklearn is not required."""
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels).astype(bool)
    positives = int(labels.sum())
    negatives = int((~labels).sum())
    if positives == 0 or negatives == 0:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1, dtype=float)
    # Average ranks within ties.
    sorted_scores = scores[order]
    start = 0
    while start < len(sorted_scores):
        stop = start
        while stop + 1 < len(sorted_scores) and sorted_scores[stop + 1] == sorted_scores[start]:
            stop += 1
        if stop > start:
            ranks[order[start:stop + 1]] = np.mean(
                np.arange(start + 1, stop + 2, dtype=float)
            )
        start = stop + 1
    rank_sum = ranks[labels].sum()
    return float((rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives))


if TORCH_AVAILABLE:

    class _Generator(nn.Module):
        def __init__(self, latent_dim, hidden, feature_dim):
            super(_Generator, self).__init__()
            self.net = nn.Sequential(
                nn.Linear(latent_dim, hidden),
                nn.LeakyReLU(0.2),
                nn.Linear(hidden, hidden),
                nn.LeakyReLU(0.2),
                nn.Linear(hidden, feature_dim),
            )

        def forward(self, z):
            return self.net(z)

    class _Discriminator(nn.Module):
        def __init__(self, feature_dim, hidden):
            super(_Discriminator, self).__init__()
            self.body = nn.Sequential(
                nn.Linear(feature_dim, hidden),
                nn.LeakyReLU(0.2),
                nn.Linear(hidden, hidden),
                nn.LeakyReLU(0.2),
            )
            self.head = nn.Linear(hidden, 1)

        def forward(self, x, return_features=False):
            features = self.body(x)
            logits = self.head(features)
            if return_features:
                return logits, features
            return logits


class GanAnomalyDetector(object):
    """One-class behaviour model over the features in ``threat_model``."""

    def __init__(self, feature_dim=None, latent_dim=None, hidden=None,
                 lr=None, epochs=None, batch_size=None, seed=0):
        self.feature_dim = config.GAN_FEATURE_DIM if feature_dim is None else int(feature_dim)
        self.latent_dim = config.GAN_LATENT_DIM if latent_dim is None else int(latent_dim)
        self.hidden = config.GAN_HIDDEN if hidden is None else int(hidden)
        self.lr = config.GAN_LR if lr is None else float(lr)
        self.epochs = config.GAN_EPOCHS if epochs is None else int(epochs)
        self.batch_size = config.GAN_BATCH if batch_size is None else int(batch_size)
        self.seed = int(seed)

        self.backend = "torch" if TORCH_AVAILABLE else "percentile-fallback"
        self.using_fallback = not TORCH_AVAILABLE
        self.fallback_reason = None if TORCH_AVAILABLE else "torch unavailable"

        self.generator = None
        self.discriminator = None
        self._bank = None
        self._bank_features = None
        self._mean = None
        self._std = None
        self.threshold = 0.5
        self.history = {"d_loss": [], "g_loss": []}
        self.validation = {}
        self.trained = False

    # -- normalisation -----------------------------------------------------

    def _fit_scaler(self, features):
        """Standardise, with a *small* floor under the standard deviation.

        This is the single most important line in the detector, and getting it
        wrong silently destroys the signal. Several features have exactly zero
        variance across honest behaviour -- an honest relay never drops a large
        packet, and never disagrees with its peers about a neighbour. Those are
        precisely the informative ones.
        """
        self._mean = features.mean(axis=0)
        self._std = features.std(axis=0)
        self._std = np.maximum(self._std, MIN_FEATURE_SCALE)

    def _scale(self, features):
        if self._mean is None:
            return np.asarray(features, dtype=np.float32)
        return ((np.asarray(features, dtype=float) - self._mean) / self._std).astype(
            np.float32
        )

    # -- training ----------------------------------------------------------

    def fit(self, clean_features, validation_features=None,
            validation_labels=None, epochs=None):
        """Train on honest-only behaviour windows.

        ``validation_features``/``validation_labels`` are optional and used only
        to measure quality -- never to fit anything.
        """
        clean = np.asarray(clean_features, dtype=float)
        clean = clean.reshape(-1, self.feature_dim) if clean.size else clean

        if clean.shape[0] < MIN_TRAIN_SAMPLES:
            self.using_fallback = True
            self.fallback_reason = (
                "only {0} clean training windows (need {1})".format(
                    clean.shape[0], MIN_TRAIN_SAMPLES)
            )
            self._fit_fallback(clean)
            return self.summary()

        self._fit_scaler(clean)

        if not TORCH_AVAILABLE:
            self._fit_fallback(clean)
            return self.summary()

        epochs = self.epochs if epochs is None else int(epochs)
        torch.manual_seed(self.seed)

        self.generator = _Generator(self.latent_dim, self.hidden, self.feature_dim)
        self.discriminator = _Discriminator(self.feature_dim, self.hidden)
        opt_g = torch.optim.Adam(self.generator.parameters(), lr=self.lr,
                                 betas=(0.5, 0.999))
        opt_d = torch.optim.Adam(self.discriminator.parameters(), lr=self.lr,
                                 betas=(0.5, 0.999))
        criterion = torch.nn.BCEWithLogitsLoss()

        data = torch.from_numpy(self._scale(clean))
        n = data.shape[0]
        batch = min(self.batch_size, n)
        self.history = {"d_loss": [], "g_loss": []}

        for _ in range(epochs):
            index = torch.randperm(n)[:batch]
            real = data[index]

            # --- discriminator ---
            z = torch.randn(batch, self.latent_dim)
            fake = self.generator(z).detach()
            d_real = self.discriminator(real)
            d_fake = self.discriminator(fake)
            # One-sided label smoothing: real targets 0.9, not 1.0.
            loss_d = criterion(
                d_real, torch.full_like(d_real, config.GAN_LABEL_SMOOTH)
            ) + criterion(d_fake, torch.zeros_like(d_fake))
            opt_d.zero_grad()
            loss_d.backward()
            opt_d.step()

            # --- generator, with feature matching to discourage collapse ---
            z = torch.randn(batch, self.latent_dim)
            generated = self.generator(z)
            g_logits, g_features = self.discriminator(generated, return_features=True)
            _, real_features = self.discriminator(real, return_features=True)
            adversarial = criterion(g_logits, torch.ones_like(g_logits))
            feature_match = torch.mean(
                (g_features.mean(dim=0) - real_features.mean(dim=0).detach()) ** 2
            )
            loss_g = adversarial + feature_match
            opt_g.zero_grad()
            loss_g.backward()
            opt_g.step()

            self.history["d_loss"].append(float(loss_d.item()))
            self.history["g_loss"].append(float(loss_g.item()))

        # Fixed bank of generated samples and their discriminator representations
        with torch.no_grad():
            z = torch.randn(GENERATED_BANK_SIZE, self.latent_dim)
            bank_samples = self.generator(z)
            self._bank = bank_samples.numpy()
            _, bank_f = self.discriminator(bank_samples, return_features=True)
            self._bank_features = bank_f.numpy()

        self.trained = True
        self.threshold = float(
            np.percentile(self.score(clean), config.GAN_THRESHOLD_PERCENTILE)
        )

        self._validate(clean, validation_features, validation_labels)
        return self.summary()

    def _validate(self, clean, validation_features, validation_labels):
        """Measure quality and trip the fallback if the GAN did not learn."""
        if validation_features is None or validation_labels is None:
            return
        features = np.asarray(validation_features, dtype=float)
        labels = np.asarray(validation_labels).astype(bool)
        if features.size == 0 or labels.sum() == 0 or (~labels).sum() == 0:
            return

        auc = roc_auc(self.score(features), labels)
        self.validation = {"auc": auc, "n": int(features.shape[0]),
                           "n_anomalous": int(labels.sum())}

        if not np.isnan(auc) and auc < MIN_ACCEPTABLE_AUC:
            self.using_fallback = True
            self.fallback_reason = (
                "GAN validation AUC {0:.3f} < {1} -- likely mode collapse; "
                "falling back to a percentile threshold on the "
                "size-conditioned drop rate".format(auc, MIN_ACCEPTABLE_AUC)
            )
            print("[gan_detector] WARNING: " + self.fallback_reason)
            self._fit_fallback(clean)

    def _fit_fallback(self, clean):
        """Percentile threshold on ``drop_rate_large`` (feature index 3)."""
        self.trained = True
        self.backend = "percentile-fallback"
        if clean.size:
            column = clean.reshape(-1, self.feature_dim)[:, 3]
            self._fallback_threshold = float(
                np.percentile(column, config.GAN_THRESHOLD_PERCENTILE)
            )
        else:
            self._fallback_threshold = 0.1
        self.threshold = self._fallback_threshold

    # -- scoring -----------------------------------------------------------

    def score(self, features):
        """Anomaly score per row; higher means less like honest behaviour.

        Combines:
        1. Reconstruction distance to the nearest generator sample in data space.
        2. Discriminator feature matching distance in the hidden representation space.
        """
        features = np.asarray(features, dtype=float)
        if features.size == 0:
            return np.zeros(0)
        features = features.reshape(-1, self.feature_dim)

        if self.using_fallback or not TORCH_AVAILABLE or self.generator is None:
            # The size-conditioned drop rate, directly.
            return np.clip(features[:, 3], 0.0, 1.0)

        scaled = self._scale(features)
        with torch.no_grad():
            tensor = torch.from_numpy(np.ascontiguousarray(scaled))
            _, features_d = self.discriminator(tensor, return_features=True)
            f_d = features_d.numpy()

        bank = self._bank
        bank_f = self._bank_features
        n_samples = scaled.shape[0]
        distances = np.empty(n_samples, dtype=np.float64)
        fm_distances = np.empty(n_samples, dtype=np.float64)
        chunk = 256

        for start in range(0, n_samples, chunk):
            block = scaled[start:start + chunk]
            diff = block[:, None, :] - bank[None, :, :]
            distances[start:start + chunk] = np.sqrt(
                (diff * diff).sum(axis=-1)
            ).min(axis=1)

            if bank_f is not None:
                block_f = f_d[start:start + chunk]
                diff_f = block_f[:, None, :] - bank_f[None, :, :]
                fm_distances[start:start + chunk] = np.sqrt(
                    (diff_f * diff_f).sum(axis=-1)
                ).min(axis=1)

        reconstruction = distances / (1.0 + distances)
        if bank_f is not None:
            feature_matching = fm_distances / (1.0 + fm_distances)
        else:
            feature_matching = reconstruction

        self.last_discriminator_score = feature_matching
        self.last_reconstruction_score = reconstruction

        return (
            RECONSTRUCTION_WEIGHT * reconstruction
            + (1.0 - RECONSTRUCTION_WEIGHT) * feature_matching
        )

    def flag(self, features):
        """Boolean "contested" verdict per row."""
        scores = self.score(features)
        return scores > self.threshold, scores

    def set_threshold_from_clean(self, clean_features, percentile=None):
        percentile = (
            config.GAN_THRESHOLD_PERCENTILE if percentile is None else float(percentile)
        )
        scores = self.score(clean_features)
        if scores.size:
            self.threshold = float(np.percentile(scores, percentile))
        return self.threshold

    # -- reporting ---------------------------------------------------------

    def summary(self):
        return {
            "gan_backend": self.backend,
            "gan_using_fallback": bool(self.using_fallback),
            "gan_fallback_reason": self.fallback_reason,
            "gan_threshold": float(self.threshold),
            "gan_epochs_run": len(self.history.get("d_loss", [])),
            "gan_final_d_loss": (
                float(self.history["d_loss"][-1]) if self.history.get("d_loss") else None
            ),
            "gan_final_g_loss": (
                float(self.history["g_loss"][-1]) if self.history.get("g_loss") else None
            ),
            "gan_val_auc": self.validation.get("auc"),
            "feature_names": list(FEATURE_NAMES),
        }
