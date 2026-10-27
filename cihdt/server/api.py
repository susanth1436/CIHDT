"""HTTP surface for the console.

Two faces on one pipeline.  This module is the JSON API: every endpoint is one
operator action, and the mapping to :class:`~cihdt.pipeline.Pipeline` is
deliberately one-to-one -- no endpoint does two steps, and no endpoint triggers
work the operator did not ask for.  :mod:`cihdt.server.pages` is the
server-rendered console that an operator actually drives, one page per step.

There is no WebSocket and no background task, and their absence is a design
consequence rather than an omission.  Nothing in this system happens on its
own, so there is never anything to push: every change to the state is the
direct result of a click.  Each JSON action therefore returns both its own
result *and* the complete new state, so a single request is enough to describe
the whole system.

The pipeline holds unsynchronised model state and CPU-bound work, so mutating
calls are serialised behind one lock and pushed to a worker thread. A thirty
second retrain never blocks the event loop.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import SETTINGS
from ..pipeline import STEP_SPEC, Pipeline, StepError
from ..schemas import PLANES
from . import auth, pages

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="CIHDT Console",
              description="Counterfactual Immunization of Holographic Digital "
                          "Twins -- a manual, step-by-step operator console for "
                          "predictive edge AI in consumer IoT networks.",
              version="1.0.0")

PIPELINE = Pipeline(seed=SETTINGS.seed)
LOCK = asyncio.Lock()


async def run(fn: Callable[..., Dict[str, Any]], *args: Any,
              **kwargs: Any) -> Dict[str, Any]:
    """Run one pipeline action and return it alongside the fresh state."""
    async with LOCK:
        try:
            result = await asyncio.to_thread(fn, *args, **kwargs)
        except StepError as exc:
            raise HTTPException(
                status_code=409,
                detail={"message": str(exc),
                        "required_step": exc.required_step}) from exc
        except Exception as exc:                             # pragma: no cover
            raise HTTPException(
                status_code=500,
                detail={"message": f"{type(exc).__name__}: {exc}",
                        "required_step": None}) from exc
        state = PIPELINE.state()
    return {"result": result, "state": state}



# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------
# Paths reachable without a session.  Deliberately short: every operator
# action has a JSON endpoint behind it, so a login screen that guards only the
# HTML would guard nothing at all.
PUBLIC_PATHS = frozenset({"/login", "/logout", "/register", "/favicon.ico"})
PUBLIC_PREFIXES = ("/static/",)


@app.middleware("http")
async def require_session(request: Request, call_next):
    """Admit a request only if it carries a live session."""
    path = request.url.path
    public = (path in PUBLIC_PATHS
              or any(path.startswith(pre) for pre in PUBLIC_PREFIXES))

    username = auth.SESSIONS.resolve(request.cookies.get(auth.COOKIE_NAME))
    user = auth.USERS.get(username) if username else None
    request.state.user = user.public() if user else None

    if public or user is not None:
        return await call_next(request)

    # An API caller wants a status it can act on; a browser wants the way in.
    wants_json = (path.startswith("/api/")
                  or "application/json" in request.headers.get("accept", ""))
    if wants_json:
        return JSONResponse(
            {"detail": {"message": "Sign in to use this console.",
                        "required_step": None}}, status_code=401)

    target = request.url.path
    if request.url.query:
        target += "?" + request.url.query
    return RedirectResponse(
        f"/login?next={quote(target, safe='/?=&')}", status_code=303)

# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class DeviceBody(BaseModel):
    device_type: str


class DeviceIdBody(BaseModel):
    device_id: str


class CollectBody(BaseModel):
    ticks: int = Field(20, ge=1, le=400)


class FuturesBody(BaseModel):
    n_futures: int = Field(SETTINGS.twin.n_futures, ge=3, le=80)
    horizon: int = Field(SETTINGS.twin.horizon, ge=1, le=20)


class CorpusBody(BaseModel):
    rows_per_class: int = Field(380, ge=80, le=1200)


class AttackBody(BaseModel):
    device_id: str
    attack: str
    duration: int = Field(25, ge=1, le=400)
    intensity: float = Field(1.0, ge=0.05, le=1.0)


class MonitorBody(BaseModel):
    ticks: int = Field(1, ge=1, le=60)


class CraftBody(BaseModel):
    strategy: str
    source: Optional[str] = None
    rows: int = Field(240, ge=40, le=1500)
    potency: float = Field(1.0, ge=0.05, le=1.0)


class UpdateIdBody(BaseModel):
    update_id: str


class ApplyBody(BaseModel):
    update_id: str
    override: Optional[str] = None       # ACCEPTED | QUARANTINED


class CalibrateBody(BaseModel):
    honest_updates: int = Field(8, ge=3, le=20)


class VaccineBody(BaseModel):
    vaccines: Optional[List[str]] = None
    scenarios: int = Field(SETTINGS.immune.scenarios_per_strategy, ge=7, le=200)


class RescoreBody(BaseModel):
    auto_release: bool = False


class RetrainBody(BaseModel):
    immunize: bool = True
    vaccines: Optional[List[str]] = None


class HealBody(BaseModel):
    reason: str = "operator-triggered"
    retrain_after: bool = True


class RollbackBody(BaseModel):
    version: int


class ReleaseBody(BaseModel):
    update_id: str
    reason: str = "operator release"


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------
@app.get("/api/catalogue")
async def api_catalogue() -> Dict[str, Any]:
    """Everything the console needs that never changes."""
    return {
        "devices": Pipeline.catalogue(),
        "strategies": Pipeline.strategies(),
        "steps": STEP_SPEC,
        "planes": {k: list(v) for k, v in PLANES.items()},
        "config": {
            "twin": {"min_fit": SETTINGS.twin.min_fit,
                     "n_futures": SETTINGS.twin.n_futures,
                     "horizon": SETTINGS.twin.horizon,
                     "window": SETTINGS.twin.window},
            "validate": {
                "obs_anomaly_threshold": SETTINGS.validate.obs_anomaly_threshold,
                "weights": {
                    "attack_agreement": SETTINGS.validate.w_attack_agreement,
                    "benign_agreement": SETTINGS.validate.w_benign_agreement,
                    "stability": SETTINGS.validate.w_stability,
                    "plane_coherence": SETTINGS.validate.w_plane_coherence,
                    "label_integrity": SETTINGS.validate.w_label_integrity,
                    "label_agreement": SETTINGS.validate.w_label_agreement,
                },
                "reputation_floor": SETTINGS.validate.reputation_floor,
            },
            "retrain": {
                "min_accuracy_gain": SETTINGS.retrain.min_accuracy_gain,
                "min_poison_resistance": SETTINGS.retrain.min_poison_resistance,
                "max_false_positive_rate": SETTINGS.retrain.max_false_positive_rate,
                "min_samples": SETTINGS.retrain.min_samples,
            },
        },
    }


@app.get("/api/state")
async def api_state() -> Dict[str, Any]:
    async with LOCK:
        return PIPELINE.state()


@app.get("/api/twin/{device_id}")
async def api_twin(device_id: str) -> Dict[str, Any]:
    async with LOCK:
        try:
            return await asyncio.to_thread(PIPELINE.twin_detail, device_id)
        except StepError as exc:
            raise HTTPException(409, {"message": str(exc),
                                      "required_step": exc.required_step})


@app.get("/api/quarantine/{update_id}")
async def api_quarantine_record(update_id: str) -> Dict[str, Any]:
    async with LOCK:
        rec = PIPELINE.quarantine.get(update_id)
        if rec is None:
            raise HTTPException(404, {"message": f"no record {update_id}"})
        return rec.as_dict()


# ---------------------------------------------------------------------------
# STEP 1 -- IoT environment
# ---------------------------------------------------------------------------
@app.post("/api/step1/add")
async def step1_add(body: DeviceBody):
    return await run(PIPELINE.add_device, body.device_type)


@app.post("/api/step1/remove")
async def step1_remove(body: DeviceIdBody):
    return await run(PIPELINE.remove_device, body.device_id)


@app.post("/api/step1/select")
async def step1_select(body: DeviceIdBody):
    return await run(PIPELINE.select_device, body.device_id)


# ---------------------------------------------------------------------------
# STEP 2 -- edge gateway
# ---------------------------------------------------------------------------
@app.post("/api/step2/start")
async def step2_start():
    return await run(PIPELINE.start_gateway)


@app.post("/api/step2/collect")
async def step2_collect(body: CollectBody):
    return await run(PIPELINE.collect, body.ticks)


# ---------------------------------------------------------------------------
# STEP 3 -- holographic twins
# ---------------------------------------------------------------------------
@app.post("/api/step3/create")
async def step3_create():
    return await run(PIPELINE.create_twins)


@app.post("/api/step3/feed")
async def step3_feed():
    return await run(PIPELINE.feed_twins)


# ---------------------------------------------------------------------------
# STEP 4 -- future prediction
# ---------------------------------------------------------------------------
@app.post("/api/step4/fit")
async def step4_fit():
    return await run(PIPELINE.fit_predictors)


# ---------------------------------------------------------------------------
# STEP 5 -- counterfactual futures
# ---------------------------------------------------------------------------
@app.post("/api/step5/futures")
async def step5_futures(body: FuturesBody):
    return await run(PIPELINE.generate_futures, body.n_futures, body.horizon)


@app.post("/api/step5/check")
async def step5_check():
    return await run(PIPELINE.counterfactual_check)


# ---------------------------------------------------------------------------
# STEP 6 -- threat detection
# ---------------------------------------------------------------------------
@app.post("/api/step6/corpus")
async def step6_corpus(body: CorpusBody):
    return await run(PIPELINE.build_training_corpus, body.rows_per_class)


@app.post("/api/step6/train")
async def step6_train():
    return await run(PIPELINE.train_detector)


@app.post("/api/step6/attack")
async def step6_attack(body: AttackBody):
    return await run(PIPELINE.launch_attack, body.device_id, body.attack,
                     body.duration, body.intensity)


@app.post("/api/step6/stop_attack")
async def step6_stop_attack(body: DeviceIdBody):
    return await run(PIPELINE.stop_attack, body.device_id)


@app.post("/api/step6/monitor")
async def step6_monitor(body: MonitorBody):
    return await run(PIPELINE.monitor, body.ticks)


# ---------------------------------------------------------------------------
# STEP 7 -- poisoning
# ---------------------------------------------------------------------------
@app.post("/api/step7/craft")
async def step7_craft(body: CraftBody):
    return await run(PIPELINE.craft_update, body.strategy, body.source,
                     body.rows, body.potency)


@app.post("/api/step7/discard")
async def step7_discard(body: UpdateIdBody):
    return await run(PIPELINE.discard_update, body.update_id)


# ---------------------------------------------------------------------------
# STEP 8 -- counterfactual validation
# ---------------------------------------------------------------------------
@app.post("/api/step8/bank")
async def step8_bank():
    return await run(PIPELINE.refresh_bank)


@app.post("/api/step8/calibrate")
async def step8_calibrate(body: CalibrateBody):
    return await run(PIPELINE.calibrate_gate, body.honest_updates)


@app.post("/api/step8/validate")
async def step8_validate(body: UpdateIdBody):
    return await run(PIPELINE.validate_update, body.update_id)


@app.post("/api/step8/apply")
async def step8_apply(body: ApplyBody):
    return await run(PIPELINE.apply_decision, body.update_id, body.override)


# ---------------------------------------------------------------------------
# STEP 9 -- immunization
# ---------------------------------------------------------------------------
@app.post("/api/step9/vaccine")
async def step9_vaccine(body: VaccineBody):
    return await run(PIPELINE.generate_vaccine, body.vaccines, body.scenarios)


@app.post("/api/step9/resistance")
async def step9_resistance():
    return await run(PIPELINE.measure_resistance)


# ---------------------------------------------------------------------------
# STEP 10 -- quarantine
# ---------------------------------------------------------------------------
@app.post("/api/step10/analyse")
async def step10_analyse(body: UpdateIdBody):
    return await run(PIPELINE.analyse_quarantined, body.update_id)


@app.post("/api/step10/release")
async def step10_release(body: ReleaseBody):
    return await run(PIPELINE.release_quarantined, body.update_id, body.reason)


@app.post("/api/step10/rescore")
async def step10_rescore(body: RescoreBody):
    return await run(PIPELINE.rescore_quarantine, body.auto_release)


# ---------------------------------------------------------------------------
# STEP 11 -- retraining
# ---------------------------------------------------------------------------
@app.post("/api/step11/retrain")
async def step11_retrain(body: RetrainBody):
    return await run(PIPELINE.retrain, body.immunize, body.vaccines)


# ---------------------------------------------------------------------------
# STEP 12 -- self-healing
# ---------------------------------------------------------------------------
@app.post("/api/step12/check")
async def step12_check():
    return await run(PIPELINE.health_check)


@app.post("/api/step12/heal")
async def step12_heal(body: HealBody):
    return await run(PIPELINE.self_heal, body.reason, body.retrain_after)


@app.post("/api/step12/rollback")
async def step12_rollback(body: RollbackBody):
    return await run(PIPELINE.rollback_to, body.version)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
@app.post("/api/reset")
async def api_reset() -> Dict[str, Any]:
    """Discard everything and return to an empty Step 1."""
    # Each route resolves ``PIPELINE`` from module scope when it runs, not at
    # import time, so rebinding this name is all a reset needs.
    global PIPELINE
    async with LOCK:
        PIPELINE = await asyncio.to_thread(Pipeline, SETTINGS.seed)
        pages.reset_view()
        return {"result": {"summary": "console reset"},
                "state": PIPELINE.state()}


class NoCacheStatic(StaticFiles):
    """Serve the stylesheet without letting the browser cache it.

    There is no build step and no content hashing in the filename, so a cached
    `styles.css` survives an edit and the browser silently keeps rendering
    yesterday's layout. Losing the cache costs nothing here -- it is one local
    file on localhost.
    """

    def is_not_modified(self, response_headers, request_headers) -> bool:
        return False

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response


if WEB_DIR.exists():
    app.mount("/static", NoCacheStatic(directory=str(WEB_DIR)), name="static")

# The server-rendered console: `/`, `/step/{n}`, `/step/{n}/{action}`, `/reset`.
# Registered last so the `/api/...` routes above always take precedence.
app.include_router(pages.router)
