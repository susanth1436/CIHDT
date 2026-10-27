"""STEP 4: the forward model each twin uses to answer "what should this device
look like next?".

A ridge-regularised vector autoregression over the last ``lags`` observations.
The choice is deliberate and worth defending: the twin has to refit constantly
from a couple of dozen observations per device on an edge box with no GPU, and
it has to produce a *distribution* of futures rather than a point estimate.
A closed-form ridge fit does that in microseconds and its residual covariance
gives the spread for free.  An LSTM would need far more data per device, would
not fit on the box, and would give a point estimate we would then have to
bootstrap anyway.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..config import SETTINGS
from ..schemas import N_FEATURES, clamp_features


class ARPredictor:
    """Ridge vector-autoregression with residual-sampled roll-out."""

    def __init__(self, lags: int = SETTINGS.twin.lags,
                 alpha: float = SETTINGS.twin.ridge_alpha) -> None:
        self.lags = int(lags)
        self.alpha = float(alpha)
        self.W: Optional[np.ndarray] = None      # (lags*F + 1, F)
        self.mu = np.zeros(N_FEATURES)
        self.sd = np.ones(N_FEATURES)
        self.resid_sd = np.ones(N_FEATURES)
        self.n_fit = 0

    @property
    def is_fitted(self) -> bool:
        return self.W is not None

    # -------------------------------------------------------------------- fit
    def fit(self, history: np.ndarray) -> "ARPredictor":
        """Fit on a (T, F) history, most recent observation last."""
        H = np.asarray(history, dtype=np.float64)
        T = H.shape[0]
        if T < self.lags + 4:
            return self

        # Standardise: features span six orders of magnitude, so an unscaled
        # fit would be dominated entirely by packet counts.
        self.mu = H.mean(axis=0)
        self.sd = H.std(axis=0)
        self.sd[self.sd < 1e-8] = 1.0
        Z = (H - self.mu) / self.sd

        rows = T - self.lags
        Xd = np.empty((rows, self.lags * N_FEATURES + 1))
        for i in range(rows):
            Xd[i, :-1] = Z[i:i + self.lags].ravel()
        Xd[:, -1] = 1.0
        Y = Z[self.lags:]

        # Closed-form ridge.  The bias column is left unpenalised.
        P = Xd.shape[1]
        reg = self.alpha * np.eye(P)
        reg[-1, -1] = 0.0
        try:
            self.W = np.linalg.solve(Xd.T @ Xd + reg, Xd.T @ Y)
        except np.linalg.LinAlgError:               # pragma: no cover
            self.W = np.linalg.pinv(Xd.T @ Xd + reg) @ Xd.T @ Y

        resid = Y - Xd @ self.W
        self.resid_sd = resid.std(axis=0)
        self.resid_sd[self.resid_sd < 1e-6] = 1e-6
        self.n_fit = rows
        return self

    # ---------------------------------------------------------------- predict
    def _step(self, window_z: np.ndarray) -> np.ndarray:
        """One step ahead in standardised space, given (lags, F) of context."""
        assert self.W is not None
        x = np.empty(self.lags * N_FEATURES + 1)
        x[:-1] = window_z.ravel()
        x[-1] = 1.0
        return x @ self.W

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        """Point prediction of the next observation, in raw feature units."""
        if not self.is_fitted:
            return np.asarray(history, dtype=np.float64)[-1].copy()
        Z = (np.asarray(history, dtype=np.float64)[-self.lags:]
             - self.mu) / self.sd
        return clamp_features(self._step(Z) * self.sd + self.mu)

    def rollout(self, history: np.ndarray, horizon: int, rng: np.random.Generator,
                noise_scale: float = SETTINGS.twin.resid_scale) -> np.ndarray:
        """One sampled future trajectory, shape (horizon, F), in raw units.

        Noise is drawn from the fitted residual spread, so the futures fan out
        exactly as much as this particular device's own history justifies --
        a rock-steady temperature sensor gets a tight cone, a bursty speaker a
        wide one.  That is what stops the consistency score from being a
        one-size-fits-all threshold.
        """
        H = np.asarray(history, dtype=np.float64)
        if not self.is_fitted:
            last = H[-1]
            jitter = rng.normal(0.0, 0.02, (horizon, N_FEATURES))
            return clamp_features(last * (1.0 + jitter))

        window = ((H[-self.lags:] - self.mu) / self.sd).copy()
        out = np.empty((horizon, N_FEATURES))
        for h in range(horizon):
            nxt = self._step(window)
            nxt = nxt + rng.normal(0.0, 1.0, N_FEATURES) * self.resid_sd * noise_scale
            out[h] = nxt
            window = np.vstack([window[1:], nxt])
        return clamp_features(out * self.sd + self.mu)
