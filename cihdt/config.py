"""Every tunable constant in one place.

Nothing in this project hides a magic number inside an algorithm.  A reviewer
should be able to read this file and know exactly what the system was
parameterised with when a result was produced.
"""
from __future__ import annotations

import os
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Both directories are written to at run time, so a deployment that mounts a
# writable volume elsewhere -- or whose application directory is read-only,
# as most container platforms' are -- points these at it rather than patching
# the source.  Unset, they sit beside the code, which is what a local
# checkout wants.
def _writable(path: Path) -> bool:
    """Can this directory actually be created and written to?

    Existing and writable are different questions on a container, where the
    application directory is usually mounted read-only.  The check writes a
    real file rather than consulting permissions, because that is the thing
    the database will attempt a moment later.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _state_dir(env_var: str, default: Path, fallback_name: str) -> Path:
    """Where run-time state goes: the chosen path, or somewhere that works.

    The database and the model registry are written while the console runs.
    Beside the code is right for a checkout and wrong for a container, whose
    application directory is read-only -- and a console that cannot open its
    database cannot serve its sign-in page, which surfaces as an internal
    error on the first request that touches an account.

    An explicit CIHDT_* path is honoured when it is usable.  Otherwise the
    temporary directory is used, which every platform guarantees is
    writable.  State there does not survive a restart, so the fallback is
    announced rather than applied quietly: losing the accounts is recoverable
    and confusing, while refusing to start is neither.
    """
    chosen = Path(os.environ.get(env_var) or default)
    if _writable(chosen):
        return chosen

    spare = Path(tempfile.gettempdir()) / "cihdt" / fallback_name
    if not _writable(spare):                                 # pragma: no cover
        raise RuntimeError(
            f"Neither {chosen} nor {spare} can be written to. Set {env_var} "
            f"to a writable directory.")
    warnings.warn(
        f"{chosen} is not writable, so {fallback_name} is being kept in "
        f"{spare} instead. It will not survive a restart -- set {env_var} to "
        f"a writable path, or a persistent disk, to keep it.",
        RuntimeWarning, stacklevel=2)
    return spare


ARTIFACTS = _state_dir("CIHDT_ARTIFACTS_DIR", ROOT / "artifacts", "artifacts")
MODEL_DIR = ARTIFACTS / "models"
DATA_DIR = _state_dir("CIHDT_DATA_DIR", ROOT / "data", "data")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

SEED = int(os.environ.get("CIHDT_SEED", "1337"))


@dataclass(frozen=True)
class TwinCfg:
    """STEP 3/4 -- holographic twin and its forward predictor."""
    window: int = 120          # observations retained per twin
    lags: int = 3              # autoregressive lags fed to the predictor
    min_fit: int = 30          # observations before the predictor will fit
    horizon: int = 5           # ticks ahead each future is rolled out
    n_futures: int = 20        # counterfactual futures per generation
    ridge_alpha: float = 1.0
    ewma_alpha: float = 0.15   # smoothing of the per-plane baselines
    resid_scale: float = 1.0   # multiplier on sampled prediction noise


@dataclass(frozen=True)
class DetectCfg:
    """STEP 6 -- edge threat-detection model."""
    n_estimators: int = 180
    max_depth: int = 16
    min_samples_leaf: int = 2
    class_weight: str = "balanced_subsample"


@dataclass(frozen=True)
class ValidateCfg:
    """STEP 8 -- counterfactual validation.  The heart of the framework."""
    # An observation whose consistency falls under this is twin-flagged.
    obs_anomaly_threshold: float = 0.35

    # Counterfactual Consistency Score weights (must sum to 1.0).
    #
    # `attack_agreement` carries the most weight because it is the question the
    # whole framework exists to ask.  `plane_coherence` and `label_integrity`
    # are close behind and deliberately independent of it: coherence is the
    # only term that catches clean-label poisoning, whose labels are honest and
    # whose effect on the bank can be small, while label_integrity is the only
    # term that catches a flip whose rows are otherwise untouched.  Removing
    # either one opens a hole a specific strategy walks straight through.
    w_attack_agreement: float = 0.30
    w_benign_agreement: float = 0.07
    w_stability: float = 0.15
    w_plane_coherence: float = 0.15
    w_label_integrity: float = 0.13
    w_label_agreement: float = 0.20

    # label_shift (total variation from the trusted prior) is mapped to an
    # integrity score by this scale: a shift of `label_shift_full` or more
    # scores zero.
    label_shift_full: float = 0.45

    # The accept threshold is calibrated from honest updates at bootstrap;
    # this is only the fallback if calibration has not been run.
    accept_threshold: float = 0.80
    threshold_z: float = 3.0          # mean(honest) - z * spread
    threshold_std_floor: float = 0.02
    threshold_floor: float = 0.55
    threshold_ceiling: float = 0.94
    calibration_updates: int = 10

    bank_size: int = 220              # futures held in the audit bank
    attack_bank_ratio: float = 0.5    # half attack-conditioned, half benign
    shadow_estimators: int = 70       # trees in the per-update shadow model

    reputation_alpha: float = 0.30    # EWMA over a source's CCS history
    reputation_floor: float = 0.70


@dataclass(frozen=True)
class ImmuneCfg:
    """STEP 9 -- predictive immunization engine."""
    scenarios_per_strategy: int = 45
    synthetic_ratio: float = 0.30     # vaccine rows / real rows
    probe_estimators: int = 90
    resistance_poison_share: float = 0.35


@dataclass(frozen=True)
class RetrainCfg:
    """STEP 11 -- promotion gates for a candidate model."""
    min_accuracy_gain: float = -0.010
    min_poison_resistance: float = 0.78
    max_false_positive_rate: float = 0.12
    min_samples: int = 200
    keep_versions: int = 10


@dataclass(frozen=True)
class HealCfg:
    """STEP 12 -- self-healing monitor."""
    window: int = 60                  # decisions per health check
    baseline_checks: int = 3
    min_flags_for_verdict: int = 5
    max_agreement_drop: float = 0.35
    min_detection_rate: float = 0.30
    max_false_negative_rate: float = 0.70
    min_health_score: float = 0.40


@dataclass(frozen=True)
class Settings:
    twin: TwinCfg = field(default_factory=TwinCfg)
    detect: DetectCfg = field(default_factory=DetectCfg)
    validate: ValidateCfg = field(default_factory=ValidateCfg)
    immune: ImmuneCfg = field(default_factory=ImmuneCfg)
    retrain: RetrainCfg = field(default_factory=RetrainCfg)
    heal: HealCfg = field(default_factory=HealCfg)
    seed: int = SEED


SETTINGS = Settings()
