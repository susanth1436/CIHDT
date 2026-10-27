"""The manual pipeline: twelve steps, none of which run by themselves.

This module is the difference between a demo that plays a movie at you and a
console you operate.  There is no background thread, no scheduler and no
autopilot anywhere in this project.  The fleet advances only when someone asks
for a tick.  Twins learn only when someone feeds them.  A model is trained only
when someone presses train, a poisoned update is crafted only when someone
crafts it, validated only when someone validates it, and its verdict is applied
to the system only when someone applies it -- and can be overruled.

Two things follow from that, and both are deliberate.

The first is pedagogical: every arrow in the architecture diagram is a button,
so the operator can stop between any two stages and inspect exactly what
crossed the boundary.

The second is a real property of the design.  Each step declares what it
requires, and :meth:`Pipeline.state` reports every step as locked, ready or
done.  Attempting a step out of order fails with a message naming the step that
has to happen first, rather than quietly producing a meaningless result -- which
matters most for the ordering the security actually depends on: futures must be
*committed before* the observation they will judge exists.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .config import MODEL_DIR, SETTINGS
from .counterfactual.bank import FutureBank, build_bank
from .counterfactual.validator import CounterfactualValidator
from .detection.model import ThreatDetector
from .explain import explain
from .immunization.engine import ImmunizationEngine
from .poisoning.attacks import STRATEGY_TEXT, PoisonForge
from .quarantine.store import QuarantineZone
from .retraining.registry import ModelRegistry
from .retraining.retrainer import SecureRetrainer
from .schemas import (ATTACK_CLASSES, ATTACK_STRATEGIES, DEVICE_TYPES,
                      FEATURES, N_FEATURES, POISON_STRATEGIES, THREAT_CLASSES,
                      ModelUpdate, Telemetry)
from .selfheal.monitor import SelfHealingMonitor
from .simulator.fleet import IoTFleet, build_corpus
from .simulator.profiles import (CATALOGUE_TEXT, DEVICE_PROFILES,
                                 SUGGESTED_LAYOUT, TYPICAL_TARGETS)
from .twin.registry import TwinRegistry

# Live mode is optional: the console still runs a simulated fleet on a host
# where psutil or WMI are unavailable, so the import must not be fatal.
try:
    from .live.device import LiveDevice, build_live_corpus
    from .live.host import PROVENANCE, HostSampler, available as live_available
    from .live.usb import UsbMonitor, UsbUnavailable
    LIVE_IMPORT_ERROR = ""
except Exception as _exc:                                    # pragma: no cover
    LiveDevice = None                                        # type: ignore
    UsbMonitor = UsbUnavailable = HostSampler = None         # type: ignore
    build_live_corpus = PROVENANCE = None                    # type: ignore
    LIVE_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"
    def live_available():                                    # type: ignore
        return False, LIVE_IMPORT_ERROR


class StepError(RuntimeError):
    """A step was attempted before its prerequisites were met."""

    def __init__(self, message: str, required_step: Optional[int] = None):
        super().__init__(message)
        self.required_step = required_step


# ---------------------------------------------------------------------------
# The twelve steps, exactly as specified in the project brief.
# ---------------------------------------------------------------------------
STEP_SPEC: List[Dict[str, Any]] = [
    {"id": 1, "key": "devices", "title": "Create the IoT environment",
     "subtitle": "Choose and deploy consumer devices",
     "purpose": "Pick devices from the catalogue and add them to the network. "
                "Everything downstream is shaped by this choice: the model is "
                "trained on the fleet you actually build.",
     "requires": []},
    {"id": 2, "key": "gateway", "title": "Start the edge gateway",
     "subtitle": "Bring up local collection",
     "purpose": "Start the gateway and collect telemetry on demand. Nothing "
                "leaves the local network, and no data is collected until you "
                "ask for a tick.",
     "requires": [1]},
    {"id": 3, "key": "twins", "title": "Build holographic digital twins",
     "subtitle": "One twin per physical device",
     "purpose": "Create a twin for each device and feed it the collected "
                "telemetry, so it learns that specific unit's normal across "
                "all five holographic planes.",
     "requires": [2]},
    {"id": 4, "key": "prediction", "title": "Predict future states",
     "subtitle": "Fit the forward model",
     "purpose": "Fit each twin's autoregressive predictor and see what it "
                "expects the device to do next.",
     "requires": [3]},
    {"id": 5, "key": "counterfactual", "title": "Generate counterfactual futures",
     "subtitle": "Commit to what should happen next",
     "purpose": "Roll out plausible futures and commit to them, then take a "
                "live tick and score reality against that commitment. The "
                "futures must exist before the observation they judge.",
     "requires": [4]},
    {"id": 6, "key": "detection", "title": "Detect threats",
     "subtitle": "Train and run the edge model",
     "purpose": "Build a labelled corpus for this fleet, train the threat "
                "detector, then launch real attacks and watch both the twin "
                "and the model respond.",
     "requires": [5]},
    {"id": 7, "key": "poisoning", "title": "Simulate model poisoning",
     "subtitle": "Craft a hostile training contribution",
     "purpose": "Craft an update using one of five poisoning strategies. It "
                "goes into the inbox and touches nothing until you validate it.",
     "requires": [6]},
    {"id": 8, "key": "validation", "title": "Counterfactual poison validation",
     "subtitle": "The framework's core mechanism",
     "purpose": "Score an update against the counterfactual bank, see every "
                "component of the decision, and then apply or overrule it.",
     "requires": [7]},
    {"id": 9, "key": "immunization", "title": "Predictive immunization",
     "subtitle": "Vaccinate before the attack",
     "purpose": "Manufacture synthetic training rows from predicted futures "
                "that inoculate the model against poisoning it has not yet met.",
     "requires": [6]},
    {"id": 10, "key": "quarantine", "title": "Quarantine and analysis",
     "subtitle": "Dissect what was held",
     "purpose": "Inspect held updates, run attack analysis on them, and "
                "release anything that turns out to be honest.",
     "requires": [8]},
    {"id": 11, "key": "retraining", "title": "Secure edge retraining",
     "subtitle": "Train on validated data only",
     "purpose": "Retrain on the safe pool plus vaccines, and promote the "
                "candidate only if it clears every gate.",
     "requires": [8]},
    {"id": 12, "key": "selfheal", "title": "Self-healing",
     "subtitle": "Detect compromise and roll back",
     "purpose": "Watch model/twin agreement, and when it collapses, roll back "
                "to the last trusted model, purge suspect data and rebuild.",
     "requires": [6]},
]
STEP_BY_ID = {s["id"]: s for s in STEP_SPEC}


class Pipeline:
    """Holds all system state and exposes one method per operator action."""

    def __init__(self, seed: int = SETTINGS.seed) -> None:
        self.seed = seed
        self.created_at = time.time()

        # --- subsystems ----------------------------------------------------
        self.fleet = IoTFleet(seed=seed)
        self.twins = TwinRegistry(seed=seed)
        self.validator = CounterfactualValidator(seed=seed)
        self.forge = PoisonForge(seed=seed + 313)
        self.quarantine = QuarantineZone()
        self.registry = ModelRegistry(root=MODEL_DIR, reset=True)
        self.immunizer = ImmunizationEngine(seed=seed)
        self.retrainer = SecureRetrainer(self.registry, self.immunizer, seed=seed)
        self.health = SelfHealingMonitor()

        # --- artefacts -----------------------------------------------------
        self.detector: Optional[ThreatDetector] = None
        self.bank = FutureBank(np.zeros((0, N_FEATURES)), np.zeros(0, np.int64),
                               np.zeros(0, np.int64))
        self.corpus: Optional[Dict[str, Any]] = None
        self.core: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]] = None
        self.eval: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]] = None
        self.train: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]] = None
        # Rows the console draws update payloads from -- held out of training,
        # so a simulated contributor is not simply handing the model its own
        # training data back and being congratulated for it.
        self.pool: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]] = None
        self.pool_idx: Optional[np.ndarray] = None
        self.vaccine: Optional[Tuple[np.ndarray, ...]] = None

        # --- telemetry source (STEP 0) ------------------------------------
        # "simulated" drives the behavioural models in cihdt.simulator;
        # "live" samples real USB peripherals through this host.  The choice
        # is made once, before Step 1, and everything after it is identical.
        self.source_mode: Optional[str] = None
        self.usb: Optional[Any] = None
        self.sampler: Optional[Any] = None
        self.live_interval = 0.35          # seconds between live samples

        # --- operator working state ---------------------------------------
        self.gateway_started = False
        self.selected_device: Optional[str] = None
        self.buffer: List[List[Telemetry]] = []      # collected, not yet fed
        self.fed_batches = 0
        self.inbox: Dict[str, Dict[str, Any]] = {}   # crafted updates awaiting work
        self.reports: List[Dict[str, Any]] = []
        self.verdict_log: List[Dict[str, Any]] = []
        self.threat_log: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.round_index = 0

        self.last_resistance: Optional[Dict[str, Any]] = None

        self.step_runs: Dict[int, int] = {s["id"]: 0 for s in STEP_SPEC}
        self.step_last: Dict[int, Dict[str, Any]] = {}
        self.stats = {"ticks": 0, "observations": 0, "detections": 0,
                      "twin_flags": 0, "attacks_launched": 0,
                      "updates_crafted": 0, "updates_validated": 0,
                      "accepted": 0, "quarantined": 0, "overrides": 0,
                      "retrains": 0, "promotions": 0, "heals": 0}

        self.log(0, "Console ready. Start at Step 1 by choosing devices.")

    # ======================================================================
    # plumbing
    # ======================================================================
    def log(self, step: int, message: str, severity: str = "info",
            payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        event = {"ts": time.time(), "step": step, "message": message,
                 "severity": severity, "payload": payload or {}}
        self.events.append(event)
        self.events = self.events[-400:]
        return event

    def _finish(self, step: int, action: str,
                result: Dict[str, Any]) -> Dict[str, Any]:
        """Mark a step as having run, and attach its post-run explanation."""
        self.step_runs[step] += 1
        self.step_last[step] = {"at": time.time(),
                                "summary": result.get("summary", "")}
        return self._explain(action, result)

    def _explain(self, action: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Attach the explanation of what this action just did.

        Every operator action returns through here, so the console and the
        terminal front end describe the same result in the same words.
        """
        card = explain(action, result, self)
        if card is not None:
            result["explanation"] = card
        return result

    def _require(self, *steps: int) -> None:
        for step in steps:
            if not self._is_done(step):
                spec = STEP_BY_ID[step]
                raise StepError(
                    f"Step {step} ({spec['title']}) has not been completed yet.",
                    required_step=step)

    # ---------------------------------------------------------- step status
    def _is_done(self, step: int) -> bool:
        if step == 1:
            return len(self.fleet) >= 1
        if step == 2:
            return self.gateway_started and self.stats["ticks"] > 0
        if step == 3:
            return len(self.twins) > 0 and self.twins.ready_count > 0
        if step == 4:
            return any(t.predictor.is_fitted for t in self.twins.twins.values())
        if step == 5:
            return self.twins.armed_count > 0 and self.step_runs[5] > 0
        if step == 6:
            return self.detector is not None and self.detector.is_fitted
        if step == 7:
            return self.stats["updates_crafted"] > 0
        if step == 8:
            return self.stats["updates_validated"] > 0
        if step == 9:
            return self.immunizer.generations > 0
        if step == 10:
            return self.quarantine.total_quarantined > 0 and self.step_runs[10] > 0
        if step == 11:
            return self.stats["retrains"] > 0
        if step == 12:
            return self.step_runs[12] > 0
        return False

    def _status(self, step: int) -> str:
        spec = STEP_BY_ID[step]
        if any(not self._is_done(r) for r in spec["requires"]):
            return "locked"
        return "done" if self._is_done(step) else "ready"

    # ======================================================================
    # STEP 0 -- choose where the telemetry comes from
    # ======================================================================
    @staticmethod
    def live_support() -> Dict[str, Any]:
        """Whether this host can sample real devices, and what it would read."""
        ok, reason = live_available()
        out: Dict[str, Any] = {"available": bool(ok), "reason": reason}
        if ok and PROVENANCE is not None:
            counts: Dict[str, int] = {}
            for _f, (prov, _how) in PROVENANCE.items():
                counts[prov] = counts.get(prov, 0) + 1
            out["provenance_counts"] = counts
            out["rows"] = [{"feature": f, "provenance": prov, "how": how}
                           for f, (prov, how) in PROVENANCE.items()]
        return out

    def choose_source(self, mode: str) -> Dict[str, Any]:
        """Pick simulated or live telemetry. The one decision before Step 1."""
        if mode not in ("simulated", "live"):
            raise StepError("Choose either the simulated fleet or live devices.")
        if len(self.fleet) and mode != self.source_mode:
            raise StepError(
                "Devices have already been deployed from the other source. "
                "Reset the console to change where telemetry comes from.")

        if mode == "live":
            ok, reason = live_available()
            if not ok:
                raise StepError(f"Live devices are not available here. {reason}")
            if self.usb is None:
                self.usb = UsbMonitor()
            if self.sampler is None:
                self.sampler = HostSampler()

        self.source_mode = mode
        self.log(0, f"Telemetry source set to {mode}.")
        return self._explain("choose_source", {
            "source_mode": mode,
            "support": self.live_support(),
            "summary": f"source: {mode}",
        })

    def scan_usb(self) -> Dict[str, Any]:
        """Re-enumerate the USB bus. Costs about a second, so it is on demand."""
        self._require_live()
        try:
            self.usb.refresh(force=True)
        except UsbUnavailable as exc:
            raise StepError(f"Could not read the USB bus. {exc}") from exc
        found = self.usb.snapshot()
        self.log(0, f"Scanned the USB bus: {len(found['present'])} device(s) "
                    f"attached.")
        return self._explain("scan_usb", {
            "usb": found,
            "enrolled": [d.device_id for d in self.fleet.devices.values()],
            "summary": f"{len(found['present'])} USB device(s) found",
        })

    def _require_live(self) -> None:
        if self.source_mode != "live":
            raise StepError("The console is not in live mode. Choose live "
                            "devices before Step 1.")
        if self.usb is None or self.sampler is None:
            raise StepError("Live sampling is not initialised. Choose the "
                            "telemetry source again.")

    def add_live_device(self, slug: str,
                        device_type: Optional[str] = None) -> Dict[str, Any]:
        """Enrol one attached USB peripheral as a monitored device."""
        self._require_live()
        if self.detector is not None:
            raise StepError(
                "The model is already trained on the current fleet. Reset the "
                "console to monitor a different device.")
        if not self.usb.devices:
            self.usb.refresh(force=True)

        usb_dev = self.usb.by_slug(slug)
        if usb_dev is None:
            raise StepError(f"No attached USB device {slug!r}. Scan again.")
        if not usb_dev.present:
            raise StepError(f"{usb_dev.name} is no longer attached.")
        if usb_dev.slug() in self.fleet.devices:
            raise StepError(f"{usb_dev.name} is already being monitored.")
        if device_type is not None and device_type not in DEVICE_TYPES:
            raise StepError(f"Device type must be one of {DEVICE_TYPES}.")

        # A sampler holds the previous counter reading, so every device
        # needs its own or the second one in a tick measures nothing.
        dev = LiveDevice(usb_dev, HostSampler(), device_type=device_type)
        self.fleet.devices[dev.device_id] = dev
        if self.selected_device is None:
            self.selected_device = dev.device_id
        self.log(1, f"Enrolled live device {usb_dev.name} "
                    f"({dev.device_type}) as {dev.device_id}.")
        return self._finish(1, "add_device", {
            "device": dev.snapshot(),
            "fleet": self.fleet.summary(),
            "live": True,
            "summary": f"{len(self.fleet)} device(s) monitored",
        })

    @property
    def is_live(self) -> bool:
        return self.source_mode == "live"

    # ======================================================================
    # STEP 1 -- create the IoT environment
    # ======================================================================
    @staticmethod
    def catalogue() -> List[Dict[str, Any]]:
        """The selectable device catalogue, built from the real profiles.

        The baseline numbers are read out of the simulator rather than written
        by hand, so the catalogue cannot drift away from how the devices
        actually behave once deployed.
        """
        show = ["cpu_usage", "net_out_kbps", "packet_rate", "conn_attempts",
                "failed_logins", "device_event_rate", "power_draw"]
        out = []
        for dtype in DEVICE_TYPES:
            profile = DEVICE_PROFILES[dtype]
            text = CATALOGUE_TEXT.get(dtype, {})
            out.append({
                "type": dtype,
                "label": text.get("label", dtype.replace("_", " ").title()),
                "icon": text.get("icon", "device"),
                "blurb": text.get("blurb", ""),
                "typical_threats": list(TYPICAL_TARGETS.get(dtype, ())),
                "suggested": SUGGESTED_LAYOUT.get(dtype, 1),
                "baseline": {f: round(profile[f][0], 2) for f in show},
            })
        return out

    def add_device(self, device_type: str) -> Dict[str, Any]:
        # Deploying a simulated device *is* choosing the simulated source, so
        # the API and the CLI need no separate call. The console still asks
        # explicitly, because there the choice is the point.
        if self.source_mode is None:
            self.source_mode = "simulated"
        if self.source_mode == "live":
            raise StepError("The console is in live mode. Enrol an attached "
                            "USB device instead of a simulated one.")
        if device_type not in DEVICE_PROFILES:
            raise StepError(f"Unknown device type {device_type!r}.")
        if len(self.fleet) >= 40:
            raise StepError("40 devices is the practical ceiling for this console.")
        if self.detector is not None:
            raise StepError(
                "The model is already trained on the current fleet. Reset the "
                "console to build a different network.")
        dev = self.fleet.add_device(device_type)
        if self.selected_device is None:
            self.selected_device = dev.device_id
        self.log(1, f"Added {dev.device_id} to the network.")
        return self._finish(1, "add_device", {
            "device": dev.snapshot(),
            "fleet": self.fleet.summary(),
            "summary": f"{len(self.fleet)} device(s) deployed",
        })

    def remove_device(self, device_id: str) -> Dict[str, Any]:
        if self.detector is not None:
            raise StepError(
                "The model is already trained on the current fleet. Reset the "
                "console to build a different network.")
        if not self.fleet.remove_device(device_id):
            raise StepError(f"No device {device_id!r} on the network.")
        self.twins.drop(device_id)
        if self.selected_device == device_id:
            self.selected_device = next(iter(self.fleet.devices), None)
        self.log(1, f"Removed {device_id} from the network.")
        return self._explain("add_device", {
            "fleet": self.fleet.summary(),
            "summary": f"{len(self.fleet)} device(s) deployed"})

    def select_device(self, device_id: str) -> Dict[str, Any]:
        """Choose the device the per-device panels operate on."""
        if device_id not in self.fleet.devices:
            raise StepError(f"No device {device_id!r} on the network.")
        self.selected_device = device_id
        return {"selected_device": device_id}

    # ======================================================================
    # STEP 2 -- edge gateway and telemetry collection
    # ======================================================================
    def start_gateway(self) -> Dict[str, Any]:
        self._require(1)
        if len(self.fleet) < 2:
            raise StepError("Deploy at least two devices before starting the "
                            "gateway.", required_step=1)
        self.gateway_started = True
        self.log(2, f"Edge gateway online for {len(self.fleet)} device(s). "
                    f"All processing stays on the local network.")
        return self._finish(2, "start_gateway", {
            "gateway": {"online": True, "devices": len(self.fleet),
                        "layout": {t: n for t, n in self.fleet.layout}},
            "summary": "gateway online",
        })

    def collect(self, ticks: int = 20) -> Dict[str, Any]:
        """Collect telemetry. Only ever runs when the operator asks."""
        self._require(1)
        if not self.gateway_started:
            raise StepError("Start the edge gateway first.", required_step=2)
        ticks = int(np.clip(ticks, 1, 400))

        if self.is_live:
            batches = []
            for i in range(ticks):
                if i:
                    time.sleep(self.live_interval)
                batches.append(self.fleet.tick())
        else:
            batches = self.fleet.collect(ticks)
        self.buffer.extend(batches)
        self.stats["ticks"] += ticks
        self.stats["observations"] += sum(len(b) for b in batches)

        latest = batches[-1] if batches else []
        self.log(2, f"Collected {ticks} tick(s): "
                    f"{sum(len(b) for b in batches)} observations.")
        return self._finish(2, "collect", {
            "ticks_collected": ticks,
            "observations": sum(len(b) for b in batches),
            "buffered_batches": len(self.buffer),
            "latest": [r.as_dict() for r in latest],
            "fleet": self.fleet.summary(),
            "summary": f"{self.stats['ticks']} ticks collected",
        })

    def device_series(self, device_id: str, feature: str = "net_out_kbps",
                      limit: int = 60) -> Dict[str, Any]:
        twin = self.twins.get(device_id)
        if twin is None or not twin.history:
            return {"device_id": device_id, "feature": feature, "series": []}
        return {"device_id": device_id, "feature": feature,
                "series": twin.series(feature, limit)}

    # ======================================================================
    # STEP 3 -- holographic twins
    # ======================================================================
    def create_twins(self) -> Dict[str, Any]:
        self._require(2)
        created = []
        for dev in self.fleet.devices.values():
            if dev.device_id not in self.twins:
                self.twins.create(dev.device_id, dev.device_type)
                created.append(dev.device_id)
        self.log(3, f"Created {len(created)} holographic twin(s).")
        return self._finish(3, "create_twins", {
            "created": created,
            "twins": self.twins.snapshot(),
            "summary": f"{len(self.twins)} twin(s)",
        })

    def feed_twins(self) -> Dict[str, Any]:
        """Fold buffered telemetry into the twins.

        This is the baseline-learning phase, so observations are trusted.  Once
        the twins are armed and a detector exists, the trust gate in
        :meth:`monitor` takes over and hostile observations are refused.
        """
        # This checks that twins *exist*, rather than calling _require(3):
        # step 3 only counts as complete once the twins are ready, and they
        # only become ready by being fed.
        if not self.twins.twins:
            raise StepError("Create the twins first.", required_step=3)
        if not self.buffer:
            raise StepError("No telemetry is buffered. Collect some in Step 2.",
                            required_step=2)
        fed = 0
        for batch in self.buffer:
            fed += self.twins.observe_batch(batch, trusted=True)
        self.fed_batches += len(self.buffer)
        self.buffer = []
        self.log(3, f"Fed {fed} observations into the twins.")
        return self._finish(3, "feed_twins", {
            "observations_fed": fed,
            "twins": self.twins.snapshot(),
            "ready": self.twins.ready_count,
            "min_fit": SETTINGS.twin.min_fit,
            "summary": f"{self.twins.ready_count}/{len(self.twins)} twins ready",
        })

    def twin_detail(self, device_id: str) -> Dict[str, Any]:
        twin = self.twins.get(device_id)
        if twin is None:
            raise StepError(f"No twin for {device_id!r}. Run Step 3.",
                            required_step=3)
        snap = twin.snapshot()
        snap["futures"] = twin.future_summary()
        snap["series"] = {f: twin.series(f, 60) for f in
                          ("cpu_usage", "net_out_kbps", "packet_rate",
                           "conn_attempts", "failed_logins", "power_draw")}
        snap["consistency_history"] = [round(c, 4)
                                       for c in twin.consistency_history][-60:]
        device = self.fleet.get(device_id)
        snap["device"] = device.snapshot() if device else None
        return snap

    # ======================================================================
    # STEP 4 -- future state prediction
    # ======================================================================
    def fit_predictors(self) -> Dict[str, Any]:
        self._require(3)
        results = self.twins.fit_all()
        fitted = [d for d, ok in results.items() if ok]
        if not fitted:
            raise StepError(
                f"No twin has the {SETTINGS.twin.min_fit} observations its "
                f"predictor needs. Collect more telemetry in Step 2 and feed "
                f"the twins again.", required_step=2)

        rows = []
        for device_id in fitted:
            twin = self.twins.twins[device_id]
            predicted = twin.predictor.predict_next(twin.matrix())
            current = twin.matrix()[-1]
            rows.append({
                "device_id": device_id,
                "device_type": twin.device_type,
                "observations": len(twin.history),
                "fit_rows": twin.predictor.n_fit,
                "compare": [
                    {"feature": f,
                     "current": round(float(current[i]), 2),
                     "predicted": round(float(predicted[i]), 2)}
                    for i, f in enumerate(FEATURES)
                    if f in ("cpu_usage", "net_out_kbps", "packet_rate",
                             "conn_attempts", "power_draw")],
            })
        self.log(4, f"Fitted forward models for {len(fitted)} twin(s).")
        return self._finish(4, "fit_predictors", {
            "fitted": fitted,
            "not_ready": [d for d, ok in results.items() if not ok],
            "predictions": rows,
            "lags": SETTINGS.twin.lags,
            "summary": f"{len(fitted)} predictor(s) fitted",
        })

    # ======================================================================
    # STEP 5 -- counterfactual futures
    # ======================================================================
    def generate_futures(self, n_futures: int = SETTINGS.twin.n_futures,
                         horizon: int = SETTINGS.twin.horizon) -> Dict[str, Any]:
        self._require(4)
        n_futures = int(np.clip(n_futures, 3, 80))
        horizon = int(np.clip(horizon, 1, 20))
        result = self.twins.arm_all(n_futures=n_futures, horizon=horizon)
        if not result["armed"]:
            raise StepError("No twin is ready to generate futures. Collect "
                            "more telemetry in Step 2.", required_step=2)
        self.log(5, f"Committed {n_futures} futures x {horizon} steps for "
                    f"{len(result['armed'])} twin(s).")
        detail = self.selected_device or result["armed"][0]
        twin = self.twins.get(detail)
        return self._explain("generate_futures", {
            **result,
            "detail_device": detail,
            "detail": twin.future_summary() if twin else {},
            "summary": f"{len(result['armed'])} twin(s) armed",
        })

    def counterfactual_check(self) -> Dict[str, Any]:
        """Take one live tick and score it against the committed futures.

        The ordering is the point: the futures were committed before this
        observation was produced, so the comparison is a genuine prediction
        test rather than a retrospective fit.
        """
        self._require(4)
        if self.twins.armed_count == 0:
            raise StepError("No twin has committed futures yet. Generate them "
                            "first.", required_step=5)

        batch = self.fleet.tick()
        self.stats["ticks"] += 1
        self.stats["observations"] += len(batch)
        scored = self.twins.score_batch(batch)

        rows, flagged = [], 0
        for rec, cf in scored:
            is_flag = (cf["ready"] and cf["consistency"]
                       < SETTINGS.validate.obs_anomaly_threshold)
            flagged += int(is_flag)
            rows.append({
                "device_id": rec.device_id,
                "device_type": rec.device_type,
                "ground_truth": rec.ground_truth,
                "consistency": round(cf["consistency"], 4),
                "deviation": round(cf.get("deviation", 0.0), 3),
                "flagged": is_flag,
                "plane_deviation": cf.get("plane_deviation", {}),
                "anomalous_planes": cf.get("anomalous_planes", []),
                "channel_deviation": cf.get("channel_deviation", {}),
                "ready": cf["ready"],
            })
            # Trust gate: an observation the twin considers hostile must not
            # become part of the twin's notion of normal.
            self.twins.twins[rec.device_id].observe(rec, trusted=not is_flag)

        self.log(5, f"Scored one live tick against committed futures: "
                    f"{flagged} deviation(s) flagged.")
        return self._finish(5, "counterfactual_check", {
            "threshold": SETTINGS.validate.obs_anomaly_threshold,
            "rows": rows,
            "flagged": flagged,
            "summary": f"{flagged}/{len(rows)} flagged",
        })

    # ======================================================================
    # STEP 6 -- threat detection
    # ======================================================================
    def build_training_corpus(self, rows_per_class: int = 380) -> Dict[str, Any]:
        """Generate a labelled corpus from the deployed fleet's own profiles."""
        self._require(2)
        rows_per_class = int(np.clip(rows_per_class, 80, 1200))
        t0 = time.perf_counter()
        if self.is_live:
            X, y, dt = build_live_corpus(self._live_baselines(),
                                         rows_per_class=rows_per_class,
                                         seed=self.seed + 13)
        else:
            X, y, dt = build_corpus(self.fleet.layout,
                                    rows_per_class=rows_per_class,
                                    seed=self.seed + 13)
        n = len(y)
        cut = int(0.62 * n)
        rng = np.random.default_rng(self.seed)

        self.train = (X[:cut], y[:cut], dt[:cut])
        rest = np.arange(cut, n)
        ev = rng.choice(rest, min(2200, len(rest)), replace=False)
        self.eval = (X[ev], y[ev], dt[ev])
        core_idx = rng.choice(cut, min(1100, cut), replace=False)
        self.core = (X[core_idx], y[core_idx], dt[core_idx])
        held = np.setdiff1d(rest, ev)
        self.pool_idx = held if len(held) > 400 else rest
        self.pool = (X[self.pool_idx], y[self.pool_idx], dt[self.pool_idx])

        self.corpus = {
            "rows": int(n), "rows_per_class": rows_per_class,
            "train_rows": int(cut), "eval_rows": int(len(ev)),
            "core_rows": int(len(core_idx)), "pool_rows": int(len(self.pool_idx)),
            "class_counts": {THREAT_CLASSES[i]: int(c)
                             for i, c in enumerate(np.bincount(
                                 y, minlength=len(THREAT_CLASSES)))},
            "layout": {t: k for t, k in self.fleet.layout},
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "source": self.source_mode or "simulated",
            "normal_from": ("measured live baseline" if self.is_live
                            else "simulated device profiles"),
            "attacks_from": "attack profiles applied to that baseline",
        }
        self.log(6, f"Built a {n}-row labelled corpus for this fleet.")
        return self._explain("build_corpus",
                             {"corpus": self.corpus, "summary": f"{n} rows"})

    def _live_baselines(self) -> Dict[str, Any]:
        """Per device type, the observations the live twins actually recorded.

        This is the measured half of the live corpus.  The rows themselves are
        handed over rather than a mean and a spread, because resampling real
        observations preserves the bursts and correlations of real host traffic
        and a Gaussian around the mean does not.  A twin without enough history
        is skipped rather than contributing a baseline it cannot support.
        """
        groups: Dict[str, List[Any]] = {}
        for device_id, twin in self.twins.twins.items():
            if twin.observations < 5 or not len(twin.history):
                continue
            groups.setdefault(twin.device_type, []).append(twin)
        if not groups:
            raise StepError(
                "No live twin has enough observations to describe normal yet. "
                "Collect more telemetry in Step 2 and feed the twins again.",
                required_step=2)

        out: Dict[str, Any] = {}
        for dtype, twins in groups.items():
            out[dtype] = np.vstack([t.matrix() for t in twins])
        return out

    def train_detector(self) -> Dict[str, Any]:
        self._require(2)
        if self.train is None:
            raise StepError("Build the training corpus first.", required_step=6)
        t0 = time.perf_counter()
        detector = ThreatDetector(seed=self.seed).fit(*self.train)
        metrics = detector.evaluate(*self.eval)
        metrics["n_train"] = int(len(self.train[1]))

        first = self.detector is None
        entry = self.registry.register(detector, metrics, poison_resistance=0.0,
                                       trusted=True,
                                       notes="initial model trained by operator")
        self.detector = detector
        self.detector.version = entry.version
        if first:
            self.retrainer.seed_pool(*self.train, source="bootstrap")
        self.validator.calibrate(self.train[0], self.train[1])
        self.health.reset_baseline("model trained")

        self.log(6, f"Trained detector v{entry.version}: accuracy "
                    f"{metrics['accuracy']:.3f}, false negatives "
                    f"{metrics['false_negative_rate']:.3f}.",
                 payload={"version": entry.version})
        return self._finish(6, "train_detector", {
            "version": entry.version,
            "metrics": metrics,
            "importances": detector.importances(10),
            "pool_size": self.retrainer.pool_size,
            "calibration": self.validator.calibration,
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "summary": f"v{entry.version}, accuracy {metrics['accuracy']:.3f}",
        })

    def launch_attack(self, device_id: str, attack: str, duration: int = 25,
                      intensity: float = 1.0) -> Dict[str, Any]:
        """Put a chosen device under a chosen attack. Entirely operator-driven."""
        self._require(1)
        device = self.fleet.get(device_id)
        if device is None:
            raise StepError(f"No device {device_id!r} on the network.")
        if attack not in ATTACK_CLASSES:
            raise StepError(f"Attack must be one of {ATTACK_CLASSES}.")
        device.start_attack(attack, duration=int(np.clip(duration, 1, 400)),
                            intensity=float(np.clip(intensity, 0.05, 1.0)))
        self.stats["attacks_launched"] += 1
        self.log(6, f"Launched {attack} against {device_id} for {duration} "
                    f"tick(s) at intensity {intensity:.2f}.", severity="warning")
        return self._explain("launch_attack", {
            "device": device.snapshot(),
            "summary": f"{attack} on {device_id}"})

    def stop_attack(self, device_id: str) -> Dict[str, Any]:
        device = self.fleet.get(device_id)
        if device is None:
            raise StepError(f"No device {device_id!r} on the network.")
        device.stop_attack()
        self.log(6, f"Stopped the attack on {device_id}.")
        return {"device": device.snapshot(), "summary": f"{device_id} clear"}

    def monitor(self, ticks: int = 1) -> Dict[str, Any]:
        """One full gateway pass: twin scores it, model classifies it, health notes it.

        This is the live protection loop from the architecture, executed one
        deliberate step at a time.
        """
        self._require(6)
        if self.twins.armed_count == 0:
            raise StepError("No twin has committed futures. Run Step 5 first.",
                            required_step=5)
        ticks = int(np.clip(ticks, 1, 60))

        rows: List[Dict[str, Any]] = []
        for _ in range(ticks):
            batch = self.fleet.tick()
            self.stats["ticks"] += 1
            self.stats["observations"] += len(batch)

            for rec, cf in self.twins.score_batch(batch):
                twin_flag = (cf["ready"] and cf["consistency"]
                             < SETTINGS.validate.obs_anomaly_threshold)
                verdict = self.detector.verdict(
                    rec, consistency=cf["consistency"],
                    plane_deviation=cf.get("plane_deviation", {}),
                    anomalous_planes=cf.get("anomalous_planes", []),
                    twin_flagged=twin_flag)
                model_flag = verdict.predicted_class != "normal"

                # Trust gate again: nothing either detector distrusts is
                # allowed to shape the twin's baseline.
                self.twins.twins[rec.device_id].observe(
                    rec, trusted=not (twin_flag or model_flag))
                self.health.record(verdict, twin_ready=cf["ready"])

                self.stats["detections"] += int(model_flag)
                self.stats["twin_flags"] += int(twin_flag)

                row = {
                    "device_id": rec.device_id,
                    "device_type": rec.device_type,
                    "predicted": verdict.predicted_class,
                    "confidence": round(verdict.confidence, 4),
                    "risk_level": verdict.risk_level,
                    "consistency": round(cf["consistency"], 4),
                    "twin_flagged": twin_flag,
                    "anomalous_planes": cf.get("anomalous_planes", []),
                    "ground_truth": rec.ground_truth,
                    "correct": ((verdict.predicted_class != "normal")
                                == (rec.ground_truth != "normal")),
                    "model_version": verdict.model_version,
                    "probabilities": verdict.probabilities,
                    "features": {f: round(float(rec.values[FEATURES.index(f)]), 2)
                                 for f in ("cpu_usage", "net_out_kbps",
                                           "packet_rate", "conn_attempts",
                                           "failed_logins", "port_diversity")},
                    "ts": verdict.timestamp,
                }
                rows.append(row)
                if model_flag or twin_flag:
                    self.threat_log.append(row)

            # Re-arm for the next tick, otherwise the futures grow stale and
            # every subsequent comparison is against an older commitment.
            self.twins.arm_all()

        self.verdict_log = (self.verdict_log + rows)[-600:]
        self.threat_log = self.threat_log[-200:]
        latest = rows[-len(self.fleet):] if rows else []
        detections = sum(1 for r in rows if r["predicted"] != "normal")
        self.log(6, f"Monitored {ticks} tick(s): {detections} threat "
                    f"detection(s) across {len(rows)} observations.",
                 severity="warning" if detections else "info")
        return self._finish(6, "monitor", {
            "ticks": ticks,
            "rows": latest,
            "all_rows": rows[-60:],
            "detections": detections,
            "threats": self.threat_log[-20:][::-1],
            "summary": f"{detections} detection(s) in {ticks} tick(s)",
        })

    # ======================================================================
    # STEP 7 -- simulate model poisoning
    # ======================================================================
    @staticmethod
    def strategies() -> List[Dict[str, Any]]:
        return [{"key": s, **STRATEGY_TEXT.get(s, {})} for s in POISON_STRATEGIES]

    def craft_update(self, strategy: str, source: Optional[str] = None,
                     rows: int = 240, potency: float = 1.0) -> Dict[str, Any]:
        """Craft a training contribution. It goes to the inbox and does nothing."""
        self._require(6)
        if strategy not in POISON_STRATEGIES:
            raise StepError(f"Strategy must be one of {POISON_STRATEGIES}.")
        if self.pool is None:
            raise StepError("Build the training corpus first.", required_step=6)

        src = source or (f"{self.selected_device or 'edge_hub'}"
                         if strategy == "clean" else f"contrib_{strategy}")
        rows = int(np.clip(rows, 40, 1500))
        updates = self.forge.craft(strategy, *self.pool, source=src, n=rows,
                                   round_index=self.round_index,
                                   potency=float(np.clip(potency, 0.05, 1.0)))

        created = []
        for u in updates:
            self.inbox[u.update_id] = {
                "update": u, "state": "pending", "report": None,
                "applied": False, "crafted_at": time.time(),
            }
            created.append(u.brief())
        self.stats["updates_crafted"] += len(updates)

        self.log(7, f"Crafted {len(updates)} {strategy} update(s) from {src}. "
                    f"Nothing has been applied -- validate them in Step 8.",
                 severity="warning" if strategy != "clean" else "info")
        return self._finish(7, "craft_update", {
            "strategy": strategy,
            "created": created,
            "inbox": self.inbox_view(),
            "summary": f"{len(updates)} update(s) in the inbox",
        })

    def inbox_view(self) -> List[Dict[str, Any]]:
        out = []
        for uid, item in sorted(self.inbox.items(),
                                key=lambda kv: -kv[1]["crafted_at"]):
            entry = item["update"].brief()
            entry.update({"state": item["state"], "applied": item["applied"]})
            if item["report"] is not None:
                r = item["report"]
                entry.update({
                    "consistency_score": r["consistency_score"],
                    "threshold": r["threshold"],
                    "decision": r["decision"],
                    "suspected_strategy": r["suspected_strategy"],
                })
            out.append(entry)
        return out

    def discard_update(self, update_id: str) -> Dict[str, Any]:
        item = self.inbox.pop(update_id, None)
        if item is None:
            raise StepError(f"No update {update_id!r} in the inbox.")
        self.log(7, f"Discarded {update_id} without validating it.")
        return {"inbox": self.inbox_view(), "summary": "discarded"}

    # ======================================================================
    # STEP 8 -- counterfactual validation
    # ======================================================================
    def refresh_bank(self) -> Dict[str, Any]:
        """Rebuild the counterfactual audit bank from current twin futures."""
        self._require(5)
        if self.twins.armed_count == 0:
            raise StepError("No twin has committed futures. Run Step 5 first.",
                            required_step=5)
        self.bank = build_bank(self.twins, trusted_detector=self.detector,
                               round_index=self.round_index, seed=self.seed)
        self.log(8, f"Rebuilt the counterfactual bank: {self.bank.n} scenarios.")
        return self._explain("refresh_bank", {
            "bank": self.bank.summary(), "samples": self.bank.sample_rows(),
            "summary": f"{self.bank.n} scenarios"})

    def calibrate_gate(self, honest_updates: int = 8) -> Dict[str, Any]:
        """Calibrate the accept threshold from honest updates on this fleet."""
        self._require(6)
        if self.bank.n == 0:
            self.refresh_bank()
        honest = [self.forge.clean_update(*self.pool, source=f"calib_{i:02d}",
                                          n=240)
                  for i in range(int(np.clip(honest_updates, 3, 20)))]
        t0 = time.perf_counter()
        cal = self.validator.calibrate_threshold(honest, self.bank,
                                                 self.detector, *self.core)
        self.log(8, f"Calibrated the accept gate on {len(honest)} honest "
                    f"updates: threshold {cal['threshold']}.")
        return self._explain("calibrate_gate", {
            "calibration": cal, "elapsed_s": round(time.perf_counter() - t0, 2),
            "summary": f"threshold {cal['threshold']}"})

    def validate_update(self, update_id: str) -> Dict[str, Any]:
        """Score an update against the counterfactual bank. Applies nothing."""
        self._require(7)
        item = self.inbox.get(update_id)
        if item is None:
            raise StepError(f"No update {update_id!r} in the inbox.")
        if item["applied"]:
            raise StepError(f"Update {update_id} has already been applied.")
        if self.bank.n == 0:
            self.refresh_bank()

        t0 = time.perf_counter()
        report = self.validator.validate(item["update"], self.bank,
                                         self.detector, *self.core)
        item["report"] = report.as_dict()
        item["state"] = "validated"
        self.stats["updates_validated"] += 1
        self.reports.insert(0, report.as_dict())
        self.reports = self.reports[:60]

        self.log(8, f"Validated {update_id}: CCS {report.consistency_score:.3f} "
                    f"vs threshold {report.threshold:.3f} -> {report.decision}"
                    f" (suspected {report.suspected_strategy}).",
                 severity="warning" if report.decision != "ACCEPTED" else "info",
                 payload={"update_id": update_id})
        return self._finish(8, "validate_update", {
            "report": item["report"],
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "inbox": self.inbox_view(),
            "summary": f"{report.decision} at CCS {report.consistency_score:.3f}",
        })

    def apply_decision(self, update_id: str,
                       override: Optional[str] = None) -> Dict[str, Any]:
        """Route a validated update to the safe pool or to quarantine.

        ``override`` lets the operator overrule the gate in either direction.
        That is not a loophole, it is the point: a security control a human
        cannot inspect and countermand is not a control, it is an oracle.  The
        override is recorded in the event log either way.
        """
        # Gated on step 7 rather than step 8: what matters is whether *this*
        # update has been validated, which the check below reports precisely.
        # Requiring step 8 would answer a first-time operator with "step 8 is
        # incomplete" when the useful answer is "validate this update first".
        self._require(7)
        item = self.inbox.get(update_id)
        if item is None:
            raise StepError(f"No update {update_id!r} in the inbox.")
        if item["report"] is None:
            raise StepError(f"Validate {update_id} before applying it.",
                            required_step=8)
        if item["applied"]:
            raise StepError(f"Update {update_id} has already been applied.")

        decision = item["report"]["decision"]
        overridden = False
        if override in ("ACCEPTED", "QUARANTINED") and override != decision:
            decision, overridden = override, True
            self.stats["overrides"] += 1

        update = item["update"]
        if decision == "ACCEPTED":
            pool_size = self.retrainer.accept(update)
            self.stats["accepted"] += 1
            message = (f"Accepted {update_id} into the safe pool "
                       f"({update.n_samples} rows; pool now {pool_size}).")
        else:
            from .schemas import ValidationReport
            self.quarantine.add(update, ValidationReport(**item["report"]))
            self.stats["quarantined"] += 1
            message = (f"Quarantined {update_id}; it is held out of the "
                       f"training pool pending analysis.")
        if overridden:
            message += " Operator overrode the automatic decision."

        item["applied"] = True
        item["state"] = f"applied:{decision}"
        self.log(8, message,
                 severity="warning" if decision != "ACCEPTED" else "info")
        return self._explain("apply_decision", {
            "decision": decision, "overridden": overridden,
            "pool_size": self.retrainer.pool_size,
            "quarantine": self.quarantine.snapshot(),
            "inbox": self.inbox_view(),
            "summary": message,
        })

    # ======================================================================
    # STEP 9 -- predictive immunization
    # ======================================================================
    def generate_vaccine(self, vaccines: Optional[List[str]] = None,
                         scenarios: int = SETTINGS.immune.scenarios_per_strategy
                         ) -> Dict[str, Any]:
        self._require(6)
        if self.bank.n == 0:
            self.refresh_bank()
        X, y, dt, w, report = self.immunizer.synthesize(
            self.bank, vaccines=vaccines,
            scenarios=int(np.clip(scenarios, 7, 200)))
        self.vaccine = (X, y, dt, w)
        self.log(9, f"Generated {report['rows']} predictive vaccine rows "
                    f"({', '.join(report.get('vaccines', []))}).")
        return self._finish(9, "generate_vaccine", {
            "vaccine": report,
            "summary": f"{report['rows']} vaccine rows",
        })

    def measure_resistance(self) -> Dict[str, Any]:
        """Rehearse every poisoning strategy against the current pool."""
        self._require(6)
        if self.bank.n == 0:
            self.refresh_bank()
        t0 = time.perf_counter()
        result = self.immunizer.poison_resistance(
            self.retrainer.X, self.retrainer.y, self.retrainer.dt, self.bank)
        self.last_resistance = result
        self.log(9, f"Measured poison resistance: "
                    f"{result['poison_resistance']:.3f} "
                    f"(weakest against {result.get('weakest')}).")
        return self._explain("measure_resistance", {
            "resistance": result,
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "summary": f"resistance {result['poison_resistance']:.3f}"})

    # ======================================================================
    # STEP 10 -- quarantine and analysis
    # ======================================================================
    def analyse_quarantined(self, update_id: str) -> Dict[str, Any]:
        self._require(8)
        rec = self.quarantine.get(update_id)
        if rec is None:
            raise StepError(f"No quarantined update {update_id!r}.")
        analysis = self.validator.forensics(rec.update, rec.report)
        rec.analysis = analysis
        self.log(10, f"Analysed {update_id}: suspected "
                     f"{analysis['suspected_strategy']}.")
        return self._finish(10, "analyse", {
            "analysis": analysis,
            "record": rec.as_dict(),
            "summary": f"suspected {analysis['suspected_strategy']}",
        })

    def release_quarantined(self, update_id: str,
                            reason: str = "operator release") -> Dict[str, Any]:
        self._require(8)
        rec = self.quarantine.release(update_id, reason=reason)
        if rec is None:
            raise StepError(f"No held update {update_id!r} to release.")
        self.retrainer.accept(rec.update)
        self.log(10, f"Released {update_id} from quarantine into the safe pool.",
                 severity="warning")
        return self._finish(10, "release", {
            "quarantine": self.quarantine.snapshot(),
            "pool_size": self.retrainer.pool_size,
            "summary": f"{update_id} released",
        })

    def rescore_quarantine(self, auto_release: bool = False) -> Dict[str, Any]:
        self._require(8)
        if not self.quarantine.held():
            raise StepError("Nothing is currently held in quarantine.")
        self.refresh_bank()
        result = self.quarantine.rescore(self.validator, self.bank,
                                         self.detector, *self.core,
                                         auto_release=auto_release)
        for uid in (result["would_pass"] if auto_release else []):
            rec = self.quarantine.get(uid)
            if rec is not None:
                self.retrainer.accept(rec.update)
        self.log(10, f"Rescored {result['rescored']} held update(s) against the "
                     f"current bank: {len(result['would_pass'])} would now pass.")
        return self._finish(10, "rescore", {
            "rescore": result,
            "quarantine": self.quarantine.snapshot(),
            "summary": f"{len(result['would_pass'])} would now pass",
        })

    # ======================================================================
    # STEP 11 -- secure retraining
    # ======================================================================
    def retrain(self, immunize: bool = True,
                vaccines: Optional[List[str]] = None) -> Dict[str, Any]:
        self._require(8)
        if self.bank.n == 0:
            self.refresh_bank()
        self.round_index += 1
        outcome = self.retrainer.retrain(
            self.bank, *self.eval, incumbent=self.detector, immunize=immunize,
            vaccines=vaccines, round_index=self.round_index,
            notes=f"operator retrain, round {self.round_index}")
        self.stats["retrains"] += 1
        if outcome.resistance and outcome.resistance.get("per_strategy"):
            self.last_resistance = outcome.resistance

        if outcome.promoted and outcome.version is not None:
            new = self.registry.load(outcome.version["version"])
            if new is not None:
                self.detector = new
            self.health.reset_baseline("model promoted")
            self.stats["promotions"] += 1
            self.log(11, f"Promoted model v{outcome.version['version']}: "
                         f"accuracy {outcome.metrics['accuracy']:.3f}, poison "
                         f"resistance "
                         f"{outcome.resistance['poison_resistance']:.3f}.")
        else:
            self.log(11, f"Candidate rejected. {outcome.reason}",
                     severity="warning")
        return self._finish(11, "retrain", {
            "outcome": outcome.as_dict(),
            "registry": self.registry.snapshot(),
            "summary": outcome.reason,
        })

    # ======================================================================
    # STEP 12 -- self-healing
    # ======================================================================
    def health_check(self) -> Dict[str, Any]:
        self._require(6)
        hc = self.health.check()
        self.log(12, ("Health check: " + ("DEGRADED -- " + "; ".join(hc.reasons)
                                          if hc.degraded else
                                          (f"healthy (score {hc.health_score:.2f})"
                                           if hc.evaluated else hc.note))),
                 severity="critical" if hc.degraded else "info")
        return self._finish(12, "health_check", {
            "check": hc.as_dict(),
            "health": self.health.snapshot(),
            "summary": ("degraded" if hc.degraded else
                        ("healthy" if hc.evaluated else "not enough evidence")),
        })

    def self_heal(self, reason: str = "operator-triggered",
                  retrain_after: bool = True,
                  force: bool = False) -> Dict[str, Any]:
        """Roll back, purge and rebuild.

        Two preconditions are checked *before* anything is touched, because
        healing is not reversible: it distrusts the running model permanently
        and removes training rows.

        The first is the health verdict.  Step 12 is about recovering from a
        model that has gone wrong, so healing one the monitor considers fine
        would distrust a model that passed every promotion gate, with no way
        to re-trust it.  ``force`` is the deliberate override, and it is
        recorded as such.

        The second is the retrain that may follow.  Retraining requires a
        validated update, and discovering that *after* the rollback has
        committed used to leave the registry changed and the request failing
        with a 409 about a step the operator never asked for.
        """
        self._require(6)

        check = self.health.last_check
        if not force and check is not None and check.evaluated \
                and not check.degraded:
            raise StepError(
                f"The monitor reports this model healthy (score "
                f"{check.health_score:.2f}). Healing would distrust a model "
                f"that is working, and nothing can re-trust it afterwards. "
                f"Run a health check after an attack, or heal anyway if you "
                f"mean to.")

        will_retrain = (retrain_after
                        and self.retrainer.pool_size >= SETTINGS.retrain.min_samples)
        if will_retrain and not self._is_done(8):
            raise StepError(
                "Healing would retrain afterwards, and retraining needs an "
                "update that has been through the gate. Validate one in Step "
                "8 first, or heal without retraining.", required_step=8)

        event = self.health.heal(self.registry, self.retrainer,
                                 self.quarantine, reason=reason)
        event["forced"] = bool(force and check is not None
                               and check.evaluated and not check.degraded)
        self.stats["heals"] += 1
        if event["rollback_available"]:
            restored = self.registry.active()
            if restored is not None:
                self.detector = restored
            self.log(12, f"COMPROMISED MODEL -- rolled back to v"
                         f"{event['rolled_back_to']}, purged "
                         f"{event['purged_rows']} suspect training row(s).",
                     severity="critical")
        else:
            self.log(12, "Health degraded but there is no earlier trusted model "
                         "to roll back to; the pool was cleaned in place.",
                     severity="critical")

        result: Dict[str, Any] = {"event": event,
                                  "registry": self.registry.snapshot()}
        if will_retrain:
            result["retrain"] = self.retrain(immunize=True)["outcome"]
        result["summary"] = (f"rolled back to v{event['rolled_back_to']}"
                             if event["rollback_available"] else "pool cleaned")
        return self._finish(12, "self_heal", result)

    def rollback_to(self, version: int) -> Dict[str, Any]:
        self._require(6)
        if not self.registry.activate(version):
            raise StepError(f"No model version {version} in the registry.")
        restored = self.registry.active()
        if restored is not None:
            self.detector = restored
        self.health.reset_baseline("manual rollback")
        self.log(12, f"Manually rolled back to model v{version}.",
                 severity="warning")
        return self._finish(12, "rollback", {
            "registry": self.registry.snapshot(),
            "summary": f"running v{version}",
        })

    # ======================================================================
    # state for the console
    # ======================================================================
    def steps(self) -> List[Dict[str, Any]]:
        out = []
        for spec in STEP_SPEC:
            sid = spec["id"]
            out.append({**spec, "status": self._status(sid),
                        "runs": self.step_runs[sid],
                        "last": self.step_last.get(sid)})
        return out

    def devices_view(self) -> List[Dict[str, Any]]:
        twins = {t["device_id"]: t for t in self.twins.snapshot()}
        out = []
        for dev in self.fleet.devices.values():
            snap = dev.snapshot()
            t = twins.get(dev.device_id, {})
            snap.update({
                "twin_exists": dev.device_id in self.twins,
                "twin_ready": t.get("ready", False),
                "twin_armed": t.get("armed", False),
                "twin_observations": t.get("observations", 0),
                "consistency": t.get("last_consistency"),
                "anomalous_planes": t.get("anomalous_planes", []),
                "typical_threats": list(TYPICAL_TARGETS.get(dev.device_type, ())),
            })
            out.append(snap)
        return out

    def state(self) -> Dict[str, Any]:
        active = (self.registry.get(self.registry.active_version)
                  if self.registry.active_version is not None else None)
        hc = self.health.last_check
        return {
            "created_at": self.created_at,
            "source_mode": self.source_mode,
            "is_live": self.is_live,
            "live_support": self.live_support(),
            "live_interval": self.live_interval,
            "usb": self.usb.snapshot() if self.usb is not None else None,
            "steps": self.steps(),
            "stats": dict(self.stats),
            "selected_device": self.selected_device,
            "devices": self.devices_view(),
            "fleet": self.fleet.summary(),
            "gateway": {"online": self.gateway_started,
                        "buffered_batches": len(self.buffer),
                        "fed_batches": self.fed_batches},
            "twins": self.twins.summary(),
            "corpus": self.corpus,
            "model": active.as_dict() if active else None,
            "registry": self.registry.snapshot(),
            "bank": self.bank.summary(),
            "validator": self.validator.snapshot(),
            "inbox": self.inbox_view(),
            "reports": self.reports[:12],
            "quarantine": self.quarantine.snapshot(),
            "retrainer": self.retrainer.snapshot(),
            "immunizer": self.immunizer.snapshot(),
            "health": self.health.snapshot(),
            "last_check": hc.as_dict() if hc else None,
            "validations": list(self.validator.history),
            "resistance": self.last_resistance,
            "threats": self.threat_log[-24:][::-1],
            "events": self.events[-90:][::-1],
            "round_index": self.round_index,
            "constants": {
                "attack_classes": ATTACK_CLASSES,
                "threat_classes": THREAT_CLASSES,
                "poison_strategies": POISON_STRATEGIES,
                "attack_strategies": ATTACK_STRATEGIES,
                "obs_threshold": SETTINGS.validate.obs_anomaly_threshold,
                "twin_min_fit": SETTINGS.twin.min_fit,
            },
        }
