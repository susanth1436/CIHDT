#!/usr/bin/env python
"""Terminal front end for the same manual pipeline the console drives.

Two modes, both useful when a browser is not to hand:

    python cli.py                 interactive -- you type each step
    python cli.py --walk          runs all twelve steps once, printing results

``--walk`` is not an autopilot sneaking back in: it is a scripted operator,
calling the same public methods in the same order the buttons do, so it also
serves as an end-to-end check that the pipeline still works.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
import time
from typing import Any, Dict, List

from cihdt.pipeline import Pipeline, StepError

BAR = "=" * 74

# Post-run explanations are on by default; --no-explain or `x` turns them off.
EXPLAIN = True


def rule(text: str = "") -> None:
    print(f"\n{BAR}\n  {text}\n{BAR}" if text else BAR)


def kv(label: str, value: Any, width: int = 30) -> None:
    print(f"  {label:<{width}} {value}")


def explain(result, width: int = 74) -> None:
    """Print the post-run explanation the pipeline attached to a result.

    Exactly the text the web console shows, from the same server-side source,
    so a walkthrough in the terminal and a walkthrough in the browser tell the
    operator the same story.
    """
    if not EXPLAIN:
        return
    e = (result or {}).get("explanation")
    if not e:
        return
    mark = {"good": "+", "warn": "!", "bad": "X"}.get(e.get("tone"), "-")
    print(f"\n  [{mark}] {e['headline']}")
    for line in e.get("what_happened", []):
        for i, chunk in enumerate(textwrap.wrap(line, width)):
            print(("      - " if i == 0 else "        ") + chunk)
    if e.get("reading"):
        print()
    for r in e.get("reading", []):
        verdict = f"   ({r['verdict']})" if r.get("verdict") else ""
        print(f"      {r['label']}: {r['value']}{verdict}")
        for chunk in textwrap.wrap(r.get("note", ""), width - 10):
            print("          " + chunk)
    if e.get("why_it_matters"):
        print("\n      WHY THIS MATTERS")
        for chunk in textwrap.wrap(e["why_it_matters"], width - 8):
            print("        " + chunk)
    if e.get("next"):
        print()
        for i, chunk in enumerate(textwrap.wrap("NEXT: " + e["next"], width - 6)):
            print("      " + chunk)


def live_fleet(p: Pipeline, limit: int = 3):
    """Enrol up to `limit` real USB peripherals attached to this machine."""
    p.choose_source("live")
    found = p.scan_usb()["usb"]["present"]
    if not found:
        raise StepError("No USB devices are attached to enrol.")
    last = None
    for dev in found[:limit]:
        last = p.add_live_device(dev["slug"])
        kv(dev["name"][:34], f"{dev['status']} -> {dev['archetype']}")
    return last


def default_fleet(p: Pipeline):
    """Deploy the standard demo fleet, returning the last add result."""
    p.choose_source("simulated")
    last = None
    for dtype, count in [("smart_camera", 2), ("smart_bulb", 2),
                         ("smart_plug", 1), ("smart_lock", 1),
                         ("temperature_sensor", 1), ("smart_speaker", 1)]:
        for _ in range(count):
            last = p.add_device(dtype)
    return last


# ---------------------------------------------------------------------------
# Scripted walk
# ---------------------------------------------------------------------------
def walk(p: Pipeline, live: bool = False) -> int:
    t0 = time.time()

    rule("STEP 1  Create the IoT environment")
    if live:
        kv("telemetry source", "live USB devices on this machine")
        added = live_fleet(p)
    else:
        added = default_fleet(p)
    for d in p.devices_view():
        kv(d["device_id"], d["device_type"])
    explain(added)
    p.select_device(next(iter(p.fleet.devices)))

    rule("STEP 2  Start the edge gateway and collect telemetry")
    kv("gateway", p.start_gateway()["gateway"]["online"])
    ticks = 40 if p.is_live else 45
    if p.is_live:
        kv("sampling", f"{ticks} ticks at {p.live_interval}s "
                       f"(~{ticks * p.live_interval:.0f}s of real time)")
    r = p.collect(ticks)
    kv("ticks collected", r["ticks_collected"])
    kv("observations", r["observations"])
    explain(r)

    rule("STEP 3  Build holographic digital twins")
    kv("twins created", len(p.create_twins()["created"]))
    r = p.feed_twins()
    kv("observations fed", r["observations_fed"])
    kv("twins ready", f"{r['ready']}/{len(p.twins)}")
    explain(r)

    rule("STEP 4  Predict future states")
    r = p.fit_predictors()
    kv("predictors fitted", len(r["fitted"]))
    first = r["predictions"][0]
    print(f"\n  {first['device_id']}:")
    for c in first["compare"]:
        print(f"    {c['feature']:<20} now {c['current']:>10.2f}"
              f"   predicted {c['predicted']:>10.2f}")
    explain(r)

    rule("STEP 5  Generate counterfactual futures and test reality")
    r = p.generate_futures()
    kv("twins armed", len(r["armed"]))
    kv("futures each", f"{r['n_futures']} x {r['horizon']} ticks")
    r = p.counterfactual_check()
    print(f"\n  {'device':<24} {'consistency':>12} {'deviation':>11}  planes")
    for row in r["rows"]:
        print(f"  {row['device_id']:<24} {row['consistency']:>12.4f} "
              f"{row['deviation']:>10.2f}s  {','.join(row['anomalous_planes']) or '-'}")
    explain(r)

    rule("STEP 6  Train the detector and detect threats")
    corpus = p.build_training_corpus(380)["corpus"]
    kv("corpus rows", corpus["rows"])
    kv("normal drawn from", corpus["normal_from"])
    r = p.train_detector()
    m = r["metrics"]
    kv("model version", f"v{r['version']}")
    kv("accuracy", f"{m['accuracy']:.4f}")
    kv("false positive rate", f"{m['false_positive_rate']:.4f}")
    kv("false negative rate", f"{m['false_negative_rate']:.4f}")
    explain(r)

    targets = list(p.fleet.devices)
    p.launch_attack(targets[0], "ddos", 12, 1.0)
    if len(targets) > 1:
        p.launch_attack(targets[1], "brute_force", 12, 0.85)
    r = p.monitor(ticks=6)
    print(f"\n  {'device':<24} {'truth':<16} {'predicted':<16} {'cf':>7}  ok")
    for row in r["rows"]:
        print(f"  {row['device_id']:<24} {row['ground_truth']:<16} "
              f"{row['predicted']:<16} {row['consistency']:>7.3f}  "
              f"{'yes' if row['correct'] else 'NO'}")
    explain(r)

    rule("STEP 8  Build the audit bank and calibrate the gate")
    kv("bank scenarios", p.refresh_bank()["bank"]["n"])
    cal_result = p.calibrate_gate(8)
    cal = cal_result["calibration"]
    kv("honest mean CCS", f"{cal['honest_mean']:.4f}")
    kv("honest spread", f"{cal['honest_std']:.4f}")
    kv("accept threshold", f"{cal['threshold']:.4f}")
    explain(cal_result)

    rule("STEP 7 + 8  Craft every strategy and audit it")
    print(f"\n  {'crafted as':<20} {'CCS':>7} {'gate':>7}  {'decision':<13}"
          f" {'suspected':<20} result")
    print("  " + "-" * 88)
    hits = total = 0
    sample = None
    for strategy in ["clean", "label_flip", "gradual_poisoning", "backdoor",
                     "sybil", "clean_label"]:
        for brief in p.craft_update(strategy, rows=240)["created"]:
            uid = brief["update_id"]
            validation = p.validate_update(uid)
            rep = validation["report"]
            if strategy == "label_flip":
                sample = validation      # explained below as a worked example
            p.apply_decision(uid)
            want = "ACCEPTED" if strategy == "clean" else "QUARANTINED"
            ok = rep["decision"] == want
            hits += ok
            total += 1
            print(f"  {strategy:<20} {rep['consistency_score']:>7.3f} "
                  f"{rep['threshold']:>7.3f}  {rep['decision']:<13} "
                  f"{rep['suspected_strategy']:<20} {'OK' if ok else 'MISSED'}")
    print(f"\n  correct decisions: {hits}/{total}")
    explain(sample)          # one worked example rather than all thirteen

    rule("STEP 9  Predictive immunization")
    v = p.generate_vaccine()["vaccine"]
    kv("vaccine rows", v["rows"])
    for kind, n in v["breakdown"].items():
        kv(f"  {kind}", n)
    res_result = p.measure_resistance()
    res = res_result["resistance"]
    kv("poison resistance", f"{res['poison_resistance']:.4f}")
    for k, val in res["per_strategy"].items():
        kv(f"  vs {k}", f"{val:.4f}")
    explain(res_result)

    rule("STEP 10  Quarantine and analysis")
    held = [r_["update_id"] for r_ in p.quarantine.snapshot()["records"]
            if not r_["released"]]
    kv("held updates", len(held))
    if held:
        a = p.analyse_quarantined(held[0])["analysis"]
        print(f"\n  {held[0]} -- suspected {a['suspected_strategy']}")
        for f in a["findings"]:
            print(f"    - {f}")

    rule("STEP 11  Secure edge retraining")
    retrain_result = p.retrain(immunize=True)
    o = retrain_result["outcome"]
    kv("outcome", "PROMOTED" if o["promoted"] else "REJECTED")
    kv("reason", o["reason"])
    for name, g in o["gates"].items():
        kv(f"  gate {name}", f"{'pass' if g['pass'] else 'FAIL'}")
    explain(retrain_result)

    rule("STEP 12  Self-healing")
    health_result = p.health_check()
    hc = health_result["check"]
    kv("evaluated", hc["evaluated"])
    if hc["evaluated"]:
        kv("health score", f"{hc['health_score']:.3f}")
        kv("model/twin agreement", f"{hc['agreement']:.3f}")
        kv("degraded", hc["degraded"])
    explain(health_result)
    # A scripted walk reaches this point with a model the monitor considers
    # healthy, and healing one of those is refused: it would distrust a model
    # that passed every gate, with nothing able to re-trust it afterwards.
    # This is a drill, so it says so rather than pretending to be a recovery.
    heal_result = p.self_heal("scripted drill", retrain_after=False,
                              force=True)
    ev = heal_result["event"]
    kv("rollback available", ev["rollback_available"])
    kv("rolled back to", ev["rolled_back_to"])
    kv("rows purged", ev["purged_rows"])
    kv("forced", f"{ev['forced']} (the model was not degraded)")
    explain(heal_result)

    rule("Summary")
    for s in p.steps():
        print(f"  step {s['id']:>2}  {s['status']:<8} {s['title']}")
    print()
    kv("elapsed", f"{time.time() - t0:.1f}s")
    return 0 if hits == total else 1


# ---------------------------------------------------------------------------
# Interactive
# ---------------------------------------------------------------------------
MENU: List[tuple] = [
    ("1", "add default fleet", lambda p, a: default_fleet(p) or {"summary": "fleet added"}),
    ("2", "start gateway", lambda p, a: p.start_gateway()),
    ("3", "collect N ticks", lambda p, a: p.collect(int(a or 45))),
    ("4", "create twins", lambda p, a: p.create_twins()),
    ("5", "feed twins", lambda p, a: p.feed_twins()),
    ("6", "fit predictors", lambda p, a: p.fit_predictors()),
    ("7", "generate futures", lambda p, a: p.generate_futures()),
    ("8", "counterfactual check", lambda p, a: p.counterfactual_check()),
    ("9", "build corpus", lambda p, a: p.build_training_corpus(int(a or 380))),
    ("10", "train detector", lambda p, a: p.train_detector()),
    ("11", "attack DEVICE ATTACK", lambda p, a: p.launch_attack(*_attack_args(a))),
    ("12", "monitor N ticks", lambda p, a: p.monitor(int(a or 5))),
    ("13", "rebuild bank", lambda p, a: p.refresh_bank()),
    ("14", "calibrate gate", lambda p, a: p.calibrate_gate(int(a or 8))),
    ("15", "craft STRATEGY", lambda p, a: p.craft_update(a or "label_flip")),
    ("16", "validate UPDATE_ID", lambda p, a: p.validate_update(a)),
    ("17", "apply UPDATE_ID", lambda p, a: p.apply_decision(a)),
    ("18", "generate vaccine", lambda p, a: p.generate_vaccine()),
    ("19", "measure resistance", lambda p, a: p.measure_resistance()),
    ("20", "analyse UPDATE_ID", lambda p, a: p.analyse_quarantined(a)),
    ("21", "retrain", lambda p, a: p.retrain()),
    ("22", "health check", lambda p, a: p.health_check()),
    ("23", "self heal [force]", lambda p, a: p.self_heal(
        "operator", force=(a or "").strip().lower() in ("force", "yes", "y"))),
]


def _attack_args(arg: str):
    parts = (arg or "").split()
    if len(parts) < 2:
        raise StepError("usage: 11 <device_id> <attack> [duration]")
    return (parts[0], parts[1], int(parts[2]) if len(parts) > 2 else 15, 1.0)


def interactive(p: Pipeline) -> int:
    global EXPLAIN
    rule("CIHDT interactive console -- nothing runs unless you ask")
    for key, label, _ in MENU:
        print(f"  {key:>3}  {label}")
    print("    s  show status      x  toggle explanations      q  quit\n")

    while True:
        try:
            raw = input("cihdt> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not raw:
            continue
        cmd, _, arg = raw.partition(" ")
        if cmd in ("q", "quit", "exit"):
            return 0
        if cmd == "x":
            EXPLAIN = not EXPLAIN
            print(f"  explanations {'on' if EXPLAIN else 'off'}")
            continue
        if cmd in ("s", "status"):
            st = p.state()
            kv("devices", st["fleet"]["n_devices"])
            kv("twins ready", f"{st['twins']['ready']}/{st['twins']['count']}")
            kv("model", f"v{st['model']['version']}" if st["model"] else "none")
            kv("safe pool", st["retrainer"]["pool_size"])
            kv("quarantined", st["quarantine"]["held"])
            for s in st["steps"]:
                print(f"    step {s['id']:>2}  {s['status']}")
            continue
        if cmd in ("h", "help", "?"):
            for key, label, _ in MENU:
                print(f"  {key:>3}  {label}")
            continue

        handler = next((fn for key, _l, fn in MENU if key == cmd), None)
        if handler is None:
            print(f"  unknown command {cmd!r} -- type h for help")
            continue
        try:
            result = handler(p, arg.strip())
            print(f"  ok: {result.get('summary', 'done')}")
            explain(result)
        except StepError as exc:
            print(f"  blocked: {exc}")
        except Exception as exc:                             # pragma: no cover
            print(f"  error: {type(exc).__name__}: {exc}")


def main() -> int:
    global EXPLAIN
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true",
                    help="run against the real USB devices on this machine")
    ap.add_argument("--walk", action="store_true",
                    help="run all twelve steps once and print the results")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--no-explain", action="store_true",
                    help="suppress the explanation printed after each step")
    args = ap.parse_args()

    global EXPLAIN
    EXPLAIN = not args.no_explain

    p = Pipeline(seed=args.seed)
    return walk(p, live=args.live) if args.walk else interactive(p)


if __name__ == "__main__":
    sys.exit(main())
