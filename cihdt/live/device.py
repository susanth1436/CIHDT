"""A real USB peripheral, presented to the rest of the pipeline as a device.

:class:`LiveDevice` carries exactly the interface
:class:`~cihdt.simulator.device.SimulatedDevice` carries, so every stage after
Step 1 -- twins, futures, detection, poisoning, retraining, healing -- works on
real hardware without knowing it is real.  The substitution is the whole point:
the framework was never about the simulator.

Two things about this class are statements rather than implementation details.

**Where the numbers come from.**  The device contributes presence, stability
and declared bus power.  Everything else is the host's, measured by
:class:`~cihdt.live.host.HostSampler`, and attributing it to this peripheral is
a modelling assumption that the console states on the page.

**What an attack means here.**  We will not attack the operator's hardware, and
we could not make a webcam mount a port scan if we wanted to.  When an attack
is launched against a live device the deformation is applied *on top of the
genuine live sample*, and every record it produces is marked ``synthetic=True``
so no result can quietly present an injected row as an observed one.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..schemas import FEATURES, N_FEATURES, Telemetry, clamp_features
from ..simulator.profiles import ATTACK_PROFILES
from .host import HostSampler
from .usb import DECLARED_POWER_W, UsbDevice


class LiveDevice:
    """One attached USB peripheral, sampled through its host."""

    def __init__(self, usb: UsbDevice, sampler: HostSampler,
                 device_type: Optional[str] = None,
                 device_id: Optional[str] = None) -> None:
        self.usb = usb
        self.sampler = sampler
        self.device_id = device_id or usb.slug()
        self.device_type = device_type or usb.archetype
        self.label = usb.name
        self.is_live = True

        self.sequence = 0
        self.created_at = time.time()
        self.last: Optional[Telemetry] = None
        self.last_synthetic = False

        # Operator-launched attack overlay (see the module docstring).
        self.attack: Optional[str] = None
        self.attack_ticks_left = 0
        self.attack_total = 0
        self.intensity = 1.0

    # ------------------------------------------------------------------ state
    @property
    def is_compromised(self) -> bool:
        return self.attack is not None and self.attack_ticks_left > 0

    @property
    def ground_truth(self) -> str:
        return self.attack if self.is_compromised else "normal"

    @property
    def present(self) -> bool:
        return self.usb.present

    def start_attack(self, attack: str, duration: int = 25,
                     intensity: float = 1.0) -> None:
        """Overlay a synthetic deformation on the live stream.

        The peripheral is not touched.  Its real telemetry keeps arriving and
        the deformation is applied to the sample, which is what lets an
        operator demonstrate detection against genuine baseline traffic without
        anybody attacking anything.
        """
        if attack not in ATTACK_PROFILES:
            raise ValueError(f"unknown attack {attack!r}")
        self.attack = attack
        self.attack_ticks_left = max(1, int(duration))
        self.attack_total = self.attack_ticks_left
        self.intensity = float(np.clip(intensity, 0.02, 1.0))

    def stop_attack(self) -> None:
        self.attack = None
        self.attack_ticks_left = 0
        self.attack_total = 0

    # ------------------------------------------------------------------- tick
    def tick(self) -> Telemetry:
        """One real observation, optionally with a synthetic overlay."""
        self.sequence += 1
        values = self.sampler.sample(self.usb)
        synthetic = False

        if self.is_compromised:
            values = self._deform(values)
            synthetic = True
            self.attack_ticks_left = max(0, self.attack_ticks_left - 1)

        values = clamp_features(values)
        for name in ("conn_attempts", "failed_logins", "unique_dst_ips",
                     "port_diversity", "reconnects"):
            i = FEATURES.index(name)
            values[i] = float(max(0.0, round(values[i])))

        rec = Telemetry(device_id=self.device_id, device_type=self.device_type,
                        timestamp=time.time(), values=values,
                        ground_truth=self.ground_truth, sequence=self.sequence)
        self.last = rec
        self.last_synthetic = synthetic
        return rec

    def _deform(self, values: np.ndarray) -> np.ndarray:
        assert self.attack is not None
        elapsed = self.attack_total - self.attack_ticks_left
        ramp = min(1.0, 0.35 + 0.65 * (elapsed / 4.0))
        strength = self.intensity * ramp
        out = values.copy()
        for feature, (mult, add) in ATTACK_PROFILES[self.attack].items():
            i = FEATURES.index(feature)
            out[i] = out[i] * (1.0 + (mult - 1.0) * strength) + add * strength
        return out

    # -------------------------------------------------------------- reporting
    def snapshot(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "label": self.label,
            "sequence": self.sequence,
            "compromised": self.is_compromised,
            "attack": self.attack if self.is_compromised else None,
            "attack_ticks_left": int(self.attack_ticks_left),
            "attack_total": int(self.attack_total),
            "intensity": round(self.intensity, 3) if self.is_compromised else None,
            "ground_truth": self.ground_truth,
            "last": self.last.as_dict() if self.last is not None else None,
            # live-only fields
            "is_live": True,
            "synthetic_last": self.last_synthetic,
            "usb": self.usb.as_dict(),
        }


# ---------------------------------------------------------------------------
# a labelled corpus grown from measured normal
# ---------------------------------------------------------------------------
def build_live_corpus(observed: Dict[str, np.ndarray],
                      rows_per_class: int = 380, seed: int = 0,
                      intensity_range: Tuple[float, float] = (0.02, 1.0)
                      ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Grow a labelled corpus from what the live devices actually did.

    Step 6 needs labelled attack rows, and there is no honest way to obtain
    them from a real peripheral: nobody is going to let us flood their webcam,
    and a webcam could not mount a port scan if we asked it to.  So *normal* is
    measured -- the benign rows are resampled from observations this machine's
    own hardware actually produced while the operator watched -- and the attack
    classes are those same real rows deformed by the profiles in
    :mod:`cihdt.simulator.profiles`.

    This is the honest half-and-half the live mode rests on, and the console
    says so on the page: the benign class is real, the hostile classes are
    synthesised on top of it.

    The intensity floor matters more here than it does for the simulated
    fleet.  A simulated corpus spans six device types whose baselines differ by
    three orders of magnitude, so a bulb under attack genuinely resembles a
    healthy camera and the problem is hard on its own.  Live devices all sample
    one host, so their baselines are nearly identical and that ambiguity
    disappears: with a floor of 0.3 every deformation separates perfectly and
    the detector scores 1.000, which measures nothing.  Rehearsing down to
    barely-perceptible intensities is what puts the hard cases back in.  The alternative -- training on a generic
    simulated baseline that looks nothing like the operator's machine -- would
    produce a detector that fires constantly on their real traffic.
    """
    from ..schemas import ATTACK_CLASSES, DEVICE_TYPE_INDEX, THREAT_INDEX

    if not observed:
        raise ValueError("no live baseline has been measured yet")

    rng = np.random.default_rng(seed)
    types = list(observed)
    classes = ["normal"] + list(ATTACK_CLASSES)
    lo, hi = intensity_range

    X_rows: List[np.ndarray] = []
    y_rows: List[int] = []
    dt_rows: List[int] = []

    for cls in classes:
        for _ in range(int(rows_per_class)):
            dtype = types[int(rng.integers(len(types)))]
            history = observed[dtype]
            # Resample a real observation rather than drawing from a Gaussian
            # around its mean.  Host traffic is bursty and multimodal, and a
            # single tight Gaussian per device makes the benign class so
            # compact that every deformation separates perfectly -- which
            # reads as 100% accuracy and means nothing.  Real rows keep the
            # correlations and the fat tail the machine actually produced.
            row = history[int(rng.integers(len(history)))].astype(np.float64)
            row = np.maximum(row * (1.0 + rng.normal(0.0, 0.08, N_FEATURES)),
                             0.0)

            if cls != "normal":
                strength = float(rng.uniform(lo, hi))
                for feature, (mult, add) in ATTACK_PROFILES[cls].items():
                    i = FEATURES.index(feature)
                    row[i] = row[i] * (1.0 + (mult - 1.0) * strength) + add * strength
                row = row * (1.0 + rng.normal(0.0, 0.05, N_FEATURES))

            X_rows.append(clamp_features(row))
            y_rows.append(THREAT_INDEX[cls])
            dt_rows.append(DEVICE_TYPE_INDEX.get(dtype, -1))

    X = np.asarray(X_rows, dtype=np.float64).reshape(-1, N_FEATURES)
    y = np.asarray(y_rows, dtype=np.int64)
    dt = np.asarray(dt_rows, dtype=np.int64)
    order = rng.permutation(len(y))
    return X[order], y[order], dt[order]
