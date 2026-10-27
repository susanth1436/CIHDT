"""Chapters 5 to 8 and Appendix A of the Project-I report.

Separated from :mod:`build_report` only because that module was already long.
Every figure quoted here was produced by the console itself and is reproducible
with `python cli.py --walk` on the versions pinned in requirements.txt.
"""
from __future__ import annotations

from docx.enum.text import WD_ALIGN_PARAGRAPH

from docx_kit import body, bullet, figure, grid, h1, h2, h3, numbered, para

J = WD_ALIGN_PARAGRAPH.JUSTIFY
C = WD_ALIGN_PARAGRAPH.CENTER


def _caption(doc, text):
    para(doc, text, size=10, italic=True, align=C, line=1.0,
         before=4, after=12)


# ===========================================================================
# 5. Methodology and Testing
# ===========================================================================
def chapter_5(doc):
    h1(doc, "5. Methodology and Testing", bookmark_name="bm_5")

    h2(doc, "5.1  Module Description", bookmark_name="bm_5_1")
    body(doc, "The system is organised as eleven Python packages, each owning "
              "one stage of the pipeline and exposing a narrow interface to "
              "the stage after it. No module reaches across more than one "
              "boundary, which is what allows the simulated fleet and the "
              "live USB sampler to be substituted for one another without any "
              "stage above Step 1 being aware of the change.")

    grid(doc, [
        ["Module", "Responsibility", "Key artefact"],
        ["simulator", "Six consumer device profiles, per-attack deformations, "
                      "and the labelled corpus generator.",
         "SimulatedDevice, build_corpus"],
        ["live", "Real USB peripherals enumerated through Windows PnP, and "
                 "host telemetry sampled with psutil.",
         "UsbMonitor, HostSampler, LiveDevice"],
        ["twin", "The holographic twin: five planes, a ridge vector-"
                 "autoregressive forward model, and committed futures.",
         "HolographicTwin, ARPredictor"],
        ["detection", "Feature engineering and the edge threat classifier.",
         "ThreatDetector, cross_plane_ratios"],
        ["counterfactual", "The audit bank of committed futures and the "
                           "Counterfactual Consistency Score.",
         "FutureBank, CounterfactualValidator"],
        ["poisoning", "Five poisoning strategies used to test the defence.",
         "PoisonForge"],
        ["immunization", "Predictive vaccines and poison-resistance "
                         "measurement.", "ImmunizationEngine"],
        ["quarantine", "Holding, dissecting, releasing and rescoring "
                       "suspicious updates.", "QuarantineZone"],
        ["retraining", "The validated safe pool, promotion gates and the "
                       "versioned model registry.",
         "SecureRetrainer, ModelRegistry"],
        ["selfheal", "Model/twin agreement monitoring, rollback and purge.",
         "SelfHealingMonitor"],
        ["server", "The operator console, the JSON API, accounts, sessions "
                   "and the audit database.",
         "pages.py, api.py, auth.py, db.py"],
    ], [1.25, 3.35, 1.90])
    _caption(doc, "Table 5.1  Module responsibilities")

    h2(doc, "5.2  Methodology", bookmark_name="bm_5_2")
    body(doc, "The framework is driven as twelve operator actions rather than "
              "as a pipeline that runs to completion. Nothing in the system "
              "advances on a timer: the fleet emits telemetry only when a tick "
              "is requested, twins learn only when they are fed, and a model "
              "update is scored only when it is submitted for validation. "
              "Each step declares its prerequisites, so an action attempted "
              "out of order fails by naming the step that has to happen first "
              "instead of quietly producing a meaningless result.")

    body(doc, "That ordering is not merely pedagogical. The security argument "
              "depends on one sequencing rule: a twin must commit to its set "
              "of plausible futures before the observation those futures will "
              "judge has been produced. If the order were reversed the "
              "comparison would be a retrospective fit rather than a "
              "prediction, and the score would carry no information.")

    h3(doc, "5.2.1  The Counterfactual Consistency Score")
    body(doc, "An incoming update is not inspected for suspicious statistics. "
              "It is grafted onto a small trusted core, a shadow model is "
              "trained on the combination, and that shadow model is placed in "
              "front of the counterfactual bank: the futures the twins "
              "committed to before the update existed, half left benign and "
              "half deformed by each attack class in the taxonomy. Six "
              "quantities are measured and combined as a weighted sum.")

    grid(doc, [
        ["Component", "Weight", "Question it asks"],
        ["attack_agreement", "0.30", "Of the attack-conditioned futures, how "
                                     "many would this update still let us "
                                     "catch?"],
        ["label_agreement", "0.20", "Do the update's labels agree with the "
                                    "trusted model's reading of its own rows?"],
        ["stability", "0.15", "How many verdicts were downgraded from attack "
                              "to normal against the incumbent?"],
        ["plane_coherence", "0.15", "Does each row obey the cross-plane "
                                    "physics of the class it claims?"],
        ["label_integrity", "0.13", "Has the label mix drifted benign-ward "
                                    "from the trusted prior?"],
        ["benign_agreement", "0.07", "Are benign futures still called "
                                     "benign?"],
    ], [1.85, 0.80, 3.85])
    _caption(doc, "Table 5.2  The six components of the Counterfactual "
                  "Consistency Score")

    body(doc, "The combination is necessary because each strategy is caught "
              "by a different term. Label flipping collapses label_integrity "
              "and attack_agreement. Clean-label poisoning leaves every label "
              "honest, so its total-variation label shift stays below 0.10 "
              "and every distributional check passes it; only label_agreement "
              "sees it. Backdoor triggers barely dent accuracy by design and "
              "are caught by the trigger-concentration signal together with "
              "plane_coherence. Removing any one component opens a hole that "
              "a specific strategy walks straight through.")

    h3(doc, "5.2.2  Calibration of the Accept Threshold")
    body(doc, "The accept threshold is not a hand-picked constant. It is "
              "measured at run time from the empirical distribution of honest "
              "updates on the deployed fleet. N honest contributions are "
              "scored through the full pipeline, and the gate is placed "
              "z = 3 standard deviations below their mean:")

    para(doc, "threshold = clip( mean(honest) − 3.0 × max(std(honest), 0.02), "
              "0.55, 0.94 )",
         size=11, align=C, line=1.0, before=6, after=10)

    body(doc, "The floor on the spread is deliberate and load-bearing. All "
              "calibration updates are drawn from one pool, so their measured "
              "spread understates how much honest traffic really varies once "
              "the fleet drifts. Without the floor the gate lands inside the "
              "honest distribution and begins quarantining legitimate "
              "contributions within a day. In the reference run the measured "
              "spread was 0.0068 and the floor of 0.02 was therefore the "
              "value used, placing the gate at 0.8568 against an honest mean "
              "of 0.9168.")

    body(doc, "One further adjustment is applied at decision time. A burst of "
              "never-before-seen contributor identities adds a novelty "
              "penalty of 0.05, capped at 0.97. Inventing identities is the "
              "entire method of a sybil flood and is the one structural "
              "signal such an attack cannot hide; the penalty tightens the "
              "gate but never decides on its own.")

    h2(doc, "5.3  Testing", bookmark_name="bm_5_3")
    body(doc, "The implementation is covered by 117 automated tests, executed "
              "with pytest. They are not limited to unit-level assertions: "
              "the majority exercise the complete pipeline, and several "
              "encode the project's central claims so that a regression in "
              "the defence would fail the build rather than pass silently.")

    grid(doc, [
        ["Area", "What the tests assert"],
        ["Simulator and twins",
         "Device types are behaviourally distinct; every attack visibly "
         "deforms telemetry; a twin becomes ready only after sufficient "
         "history; futures are committed before scoring; the trust gate keeps "
         "hostile observations out of the twin's baseline; plane deviation "
         "localises the attack."],
        ["Detection",
         "Engineered features are finite; cross-plane ratios detect physical "
         "inconsistency; the detector separates normal from attack; "
         "probabilities span the full taxonomy."],
        ["Counterfactual validation",
         "Honest updates are accepted; every one of the five poisoning "
         "strategies is quarantined; poisoned scores sit below honest scores "
         "by a clear margin; clean-label poisoning is caught by "
         "label_agreement; the validator never reads the declared strategy; "
         "the threshold is calibrated rather than hard-coded."],
        ["Immunization and retraining",
         "Vaccines are always labelled as attacks and are physically valid; "
         "poison resistance is measured per strategy; a degraded candidate is "
         "refused promotion; pool provenance allows a surgical purge."],
        ["Self-healing",
         "The registry rolls back to the last trusted version; the monitor "
         "requires evidence before judging; a blinded model is detected; "
         "healing checks its preconditions before committing; a healthy model "
         "is not healed without an explicit override."],
        ["Console and ordering",
         "Steps start locked and unlock in order; an out-of-order action "
         "names the blocking step; nothing advances without being asked; "
         "every action returns a well-formed, derived explanation."],
        ["Web interface",
         "Each step is its own document; no JavaScript is served; an action "
         "redirects to its own panel so the operator does not lose their "
         "place; no redirect omits its fragment; nothing is pinned wider than "
         "a phone screen."],
        ["Access control and storage",
         "Every page and every API endpoint is behind a session; passwords "
         "never appear in the database file; sign-in failures do not "
         "enumerate accounts; an open redirect is refused; foreign keys "
         "cascade; sessions survive a restart; every action is audited."],
    ], [1.55, 4.95])
    _caption(doc, "Table 5.3  Test coverage by area")

    body(doc, "In addition to the automated suite, the terminal front end "
              "doubles as an end-to-end check. The command `python cli.py "
              "--walk` drives all twelve steps in order through the same "
              "public methods the console buttons call, and exits with a "
              "non-zero status if any validation decision comes out wrong. A "
              "successful run is therefore evidence that the framework's "
              "central claim still holds, not merely that the code executes.")


# ===========================================================================
# 6. Project Demonstration
# ===========================================================================
def chapter_6(doc):
    h1(doc, "6. Project Demonstration", bookmark_name="bm_6")

    body(doc, "The system is demonstrated through a web console served from "
              "the edge gateway itself. The console is deliberately a "
              "multi-page application: each of the twelve steps is a distinct "
              "page at its own address, and every control is an HTML form "
              "that submits one operator action and redirects back to the "
              "panel it was pressed on. No JavaScript is served at all.")

    body(doc, "That shape follows from the system's premise rather than from "
              "a preference. Because nothing happens unless the operator asks "
              "for it, there is never any state to push to the browser; and "
              "because every action is a POST followed by a redirect, a page "
              "refresh re-reads the result instead of silently repeating the "
              "action. On a console able to retrain and roll back a deployed "
              "model, that distinction matters.")

    h2(doc, "6.1  Access Control", bookmark_name="bm_6_1")
    body(doc, "Every operator signs in with an email address, and the gate "
              "covers the JSON API as well as the pages: a login screen in "
              "front of the HTML alone would protect nothing, because every "
              "operator action also has an endpoint behind it. Passwords are "
              "stored only as a salted PBKDF2-HMAC-SHA256 derivation at "
              "240,000 iterations and verified in constant time; no default "
              "credential exists anywhere in the source tree. Sessions are "
              "held server-side in the database, so signing out genuinely "
              "ends a session and a restart does not interrupt a walkthrough "
              "in progress.")

    h2(doc, "6.2  Walking the Twelve Steps", bookmark_name="bm_6_2")
    body(doc, "The operator chooses a telemetry source, assembles a fleet one "
              "device at a time, brings up the gateway and collects "
              "telemetry on demand. Twins are created and fed, forward models "
              "are fitted, and futures are committed. From Step 6 onward the "
              "detector is trained on a corpus generated from the deployed "
              "fleet's own profiles, attacks are launched by hand against "
              "named devices, and the protection loop is run one tick at a "
              "time so that the twin's judgement and the model's judgement "
              "can be compared directly.")

    body(doc, "Steps 7 and 8 are the core of the demonstration. A poisoned "
              "contribution is crafted using any of five strategies and lands "
              "in an inbox where it touches nothing. Validating it produces "
              "the Counterfactual Consistency Score together with every "
              "component that went into it, the bank classes that would be "
              "lost if it were accepted, and the strategy attribution scores. "
              "The verdict is a recommendation until the operator applies it, "
              "and it can be overruled in either direction — the override "
              "being recorded in the audit trail either way, because a "
              "security control a human cannot inspect and countermand is not "
              "a control but an oracle.")

    body(doc, "After every action the console presents a “what just "
              "happened” card generated from the numbers that action "
              "actually produced: a headline stating the outcome, bullets "
              "quoting real values, the key readings with plain-English "
              "notes, and a pointer to the next step. The text is produced "
              "server-side so the browser console and the terminal front end "
              "tell the operator the same story from one source.")

    h2(doc, "6.3  Demonstration on Live USB Hardware", bookmark_name="bm_6_3")
    body(doc, "Before Step 1 the console asks a single question: should the "
              "telemetry come from the simulated fleet, or from the real USB "
              "devices attached to this machine? Choosing live enumerates the "
              "USB bus through Windows PnP, and attached peripherals — a "
              "webcam, a Bluetooth radio, a composite device — can be "
              "enrolled by name. Every step from that point onward behaves "
              "identically, which is the point: the twelve steps do not know "
              "whether the numbers they are reading came from a behavioural "
              "model or from the bus of a laptop.")

    body(doc, "The console is explicit about what live mode can and cannot "
              "measure, and displays the complete sixteen-feature vector for "
              "each collected tick with the provenance of every value. Ten "
              "features are measured from the host, three from the peripheral "
              "itself, one is declared by the USB specification rather than "
              "measured, and two cannot be obtained on an unprivileged "
              "Windows host at all. Those two are held at zero and reported "
              "as missing, never invented.")

    h2(doc, "6.4  Conclusion of a Run", bookmark_name="bm_6_4")
    body(doc, "On completion of all twelve steps the console presents a "
              "results page that gathers the evidence into a single verdict: "
              "the number of validation decisions that were correct, the "
              "headline detection figures, the full decision table, the "
              "poison-resistance measurements, and an explicit statement of "
              "what the run does not establish. The run can be exported as "
              "JSON or as a CSV decision table so that reported figures are "
              "transferred as data rather than transcribed by hand.")


# ===========================================================================
# 7. Result and Discussion
# ===========================================================================
def chapter_7(doc):
    h1(doc, "7. Result and Discussion", bookmark_name="bm_7")

    body(doc, "All figures in this chapter were produced by the system on a "
              "mixed eight-device fleet comprising two smart cameras, two "
              "smart bulbs, a smart plug, a smart lock, a temperature sensor "
              "and a smart speaker, with seed 1337. The run is reproducible "
              "with `python cli.py --walk` on the library versions pinned in "
              "requirements.txt.")

    h2(doc, "7.1  Threat Detection Performance", bookmark_name="bm_7_1")
    grid(doc, [
        ["Metric", "Value", "Interpretation"],
        ["Accuracy", "0.9565", "Overall classification across seven classes"],
        ["Macro F1", "0.9564", "Unweighted mean, so rare classes count "
                               "equally"],
        ["False positive rate", "0.0488", "Benign traffic called hostile"],
        ["False negative rate", "0.0307", "Attack called benign — the "
                                          "failure mode poisoning aims to "
                                          "produce"],
    ], [1.75, 1.00, 3.75])
    _caption(doc, "Table 7.1  Edge detector performance on held-out "
                  "evaluation data")

    body(doc, "The two error rates are reported separately because they are "
              "not interchangeable. A high false-positive rate drives an "
              "operator to switch the system off; a high false-negative rate "
              "is precisely the condition a poisoning attack is engineered to "
              "create. The promotion gate in Step 11 therefore constrains "
              "the false-positive rate directly rather than relying on "
              "accuracy alone.")

    h2(doc, "7.2  Twin Consistency", bookmark_name="bm_7_2")
    body(doc, "Normal traffic never falls below the 0.35 flag threshold "
              "across the fleet, while attacks at full intensity are flagged "
              "approximately 92% of the time. During live monitoring the "
              "consistency of a device under data exfiltration collapsed to "
              "0.055 while its unaffected neighbours remained at 0.87, and "
              "the anomalous plane named the character of the attack: a port "
              "scan detonates the topology plane while leaving resources "
              "untouched, and a firmware tamper does the opposite.")

    h2(doc, "7.3  Counterfactual Validation", bookmark_name="bm_7_3")
    body(doc, "This is the central result. Eight honest contributions "
              "produced a mean Counterfactual Consistency Score of 0.9168 "
              "with a standard deviation of 0.0068, against an audit bank of "
              "187 scenarios. The calibrated accept threshold was therefore "
              "0.8568. Thirteen contributions were then submitted, one "
              "honest and twelve hostile across the five strategies.")

    grid(doc, [
        ["Crafted as", "CCS", "Gate", "Decision", "Attributed as"],
        ["Honest contribution", "0.910", "0.857", "ACCEPTED", "clean"],
        ["Label flipping", "0.629", "0.857", "QUARANTINED", "label_flip"],
        ["Gradual poisoning", "0.801", "0.857", "QUARANTINED",
         "gradual_poisoning"],
        ["Backdoor trigger", "0.659", "0.857", "QUARANTINED", "backdoor"],
        ["Sybil flood (8 shards)", "0.677–0.730", "0.857 / 0.907",
         "QUARANTINED", "sybil"],
        ["Clean-label poisoning", "0.735", "0.907", "QUARANTINED",
         "clean_label"],
    ], [1.60, 0.95, 1.05, 1.25, 1.65])
    _caption(doc, "Table 7.2  Validation decisions, 13 of 13 correct")

    body(doc, "Thirteen of thirteen decisions were correct. No honest update "
              "was rejected and no poisoning strategy was admitted. Two rows "
              "warrant comment. The gate shown for most sybil shards is 0.907 "
              "rather than 0.857 because the burst of previously unseen "
              "contributor identities triggered the novelty penalty described "
              "in Section 5.2.2. The clean-label row is the result that "
              "distinguishes this framework from distributional defences: "
              "its label mix barely moves, so every check based on label "
              "distribution admits it, and it is caught only by the "
              "cross-check of its labels against the trusted model's reading "
              "of its own rows.")

    h2(doc, "7.4  Immunization and Promotion", bookmark_name="bm_7_4")
    body(doc, "Measured poison resistance across the five rehearsed "
              "strategies was 0.9736, weakest against backdoor and "
              "clean-label poisoning at 0.9528 each. The retrained candidate "
              "cleared all four promotion gates — accuracy regression, "
              "poison-resistance floor, false-positive ceiling and minimum "
              "pool size — and was promoted as model version 2. The "
              "poison-resistance gate is the one that earns its place in that "
              "set: a backdoored model scores excellently on accuracy, "
              "because producing exactly that outcome is the purpose of a "
              "backdoor.")

    h2(doc, "7.5  Results on Live USB Hardware", bookmark_name="bm_7_5")
    grid(doc, [
        ["Metric", "Live USB devices", "Simulated fleet"],
        ["Accuracy", "0.9962", "0.9565"],
        ["Macro F1", "0.9961", "0.9564"],
        ["False positive rate", "0.0000", "0.0488"],
        ["False negative rate", "0.0029", "0.0307"],
        ["Validation decisions", "13 of 13", "13 of 13"],
    ], [1.95, 1.75, 1.75])
    _caption(doc, "Table 7.3  Live hardware compared with the simulated "
                  "fleet")

    body(doc, "The live figures are higher, and that difference must be read "
              "carefully: it reflects an easier problem, not a better model. "
              "The simulated fleet spans six device types whose baselines "
              "differ by three orders of magnitude, so a weakly attacked bulb "
              "genuinely resembles a healthy camera and the classes overlap. "
              "Live USB peripherals all sample a single host, so their "
              "baselines are nearly identical and that ambiguity disappears. "
              "An initial live build scored a meaningless 1.0000; it required "
              "resampling real observations for the benign class and "
              "rehearsing attacks down to 2% intensity before the metric "
              "discriminated anything at all.")

    h2(doc, "7.6  Cost Analysis", bookmark_name="bm_7_6")
    body(doc, "The system was developed and evaluated entirely on commodity "
              "hardware with no purchased software, no cloud compute and no "
              "paid data. Every dependency is open source. A complete "
              "twelve-step run, including corpus generation, detector "
              "training, thirteen validations, vaccine synthesis, "
              "poison-resistance rehearsal and a retrain, completes in "
              "approximately 17 seconds on a laptop-class machine without a "
              "GPU. Live sampling adds real elapsed time only because it "
              "waits for genuine sampling intervals: forty paced samples "
              "take approximately 12 seconds.")

    body(doc, "The direct monetary cost of the project is therefore nil. The "
              "relevant operational cost is the retraining budget on the edge "
              "gateway itself, and the architectural choices were made to "
              "keep that small: a random forest retrains from scratch in "
              "about a second, and the twin's forward model is a closed-form "
              "ridge fit rather than a network requiring gradient descent.")

    h2(doc, "7.7  Discussion", bookmark_name="bm_7_7")
    body(doc, "The results support the central claim: validating a model "
              "update against futures committed before that update existed "
              "separates honest contributions from poisoned ones more "
              "reliably than inspecting the update's own statistics, and it "
              "does so for strategies specifically designed to defeat "
              "statistical inspection. The clean-label result is the "
              "strongest single piece of evidence, because that strategy is "
              "constructed so that no label-distribution test can see it.")

    body(doc, "Four limitations are stated explicitly, since each is a "
              "question a careful reader should ask. First, the simulated "
              "fleet is generated from physically motivated behavioural "
              "profiles, not captured from real hardware; the live mode "
              "addresses this only partially, because a USB peripheral has no "
              "network stack of its own and its network planes are therefore "
              "measured on the host and attributed to it. Second, poison "
              "resistance is measured against the five rehearsed strategies, "
              "and an attacker employing a sixth lies outside that figure. "
              "Third, strategy attribution is rule-based rather than learned, "
              "because a learned attributor would require labelled poison to "
              "train on, and the availability of such labels would remove the "
              "need for the defence. Fourth, the label_agreement term trusts "
              "the incumbent model, so an update carrying a genuinely novel "
              "attack pattern would be penalised by that term; it is one of "
              "six for precisely this reason, and the counterfactual terms "
              "exist to judge damage the incumbent cannot see.")


# ===========================================================================
# 8. Conclusion
# ===========================================================================
def chapter_8(doc):
    h1(doc, "8. Conclusion", bookmark_name="bm_8")

    body(doc, "This project set out to address a specific weakness in "
              "federated and distributed model updating for consumer IoT "
              "security: existing defences judge an incoming contribution by "
              "how closely it resembles the others, which is a question about "
              "the present and the past, and one that an attacker answers "
              "simply by staying close to the crowd.")

    body(doc, "The framework developed here asks a different question. Each "
              "device is mirrored by a holographic digital twin that holds "
              "five partial projections of the device rather than one state "
              "vector, and that twin commits in advance to a set of futures "
              "the device would plausibly follow. An incoming update is then "
              "judged not by its appearance but by its consequence: it is "
              "grafted onto a trusted core, a shadow model is trained, and "
              "that shadow is measured against those committed futures. The "
              "question becomes what accepting this update would cost our "
              "ability to detect tomorrow's attack.")

    body(doc, "The implementation demonstrates the claim end to end. On a "
              "mixed eight-device fleet the edge detector reached 0.9565 "
              "accuracy with a 0.0307 false-negative rate; the accept "
              "threshold was calibrated at run time to 0.8568 from the "
              "observed distribution of honest contributions rather than "
              "chosen by hand; and all thirteen validation decisions were "
              "correct, admitting the honest contribution and rejecting every "
              "one of the five poisoning strategies, including clean-label "
              "poisoning whose label distribution is indistinguishable from "
              "honest data. Measured poison resistance reached 0.9736, and "
              "the retrained model cleared all four promotion gates.")

    body(doc, "The framework was further shown to be independent of its data "
              "source. Real USB peripherals attached to a laptop were "
              "enrolled and monitored through the identical twelve stages, "
              "with the provenance of every one of the sixteen features "
              "declared on screen and the two features that cannot be "
              "obtained reported as missing rather than fabricated. That "
              "substitution is the strongest available evidence that the "
              "contribution lies in the decision mechanism and not in the "
              "simulator.")

    h2(doc, "8.1  Contributions", bookmark_name="bm_8_1")
    numbered(doc, "A counterfactual validation mechanism that judges a model "
                  "update by its effect on futures committed before the "
                  "update existed, rather than by its own statistics.")
    numbered(doc, "A six-component Counterfactual Consistency Score in which "
                  "each term closes a hole the others leave open, "
                  "demonstrated against five distinct poisoning strategies.")
    numbered(doc, "A run-time threshold calibration procedure that adapts the "
                  "accept gate to the deployed fleet instead of requiring the "
                  "fleet to suit a fixed constant.")
    numbered(doc, "A predictive immunization engine that manufactures "
                  "training rows from predicted futures, inoculating the edge "
                  "model against poisoning it has not yet encountered.")
    numbered(doc, "A complete operator console in which every stage is a "
                  "deliberate action with declared prerequisites, allowing "
                  "the boundary between any two stages to be inspected.")

    h2(doc, "8.2  Future Work", bookmark_name="bm_8_2")
    bullet(doc, "Deployment against genuine networked IoT hardware — a "
                "camera or smart plug with its own address on a real wireless "
                "network — which would remove the host-attribution assumption "
                "that live USB mode currently requires.")
    bullet(doc, "Extension of the poisoning taxonomy beyond the five "
                "rehearsed strategies, and investigation of an adaptive "
                "adversary with knowledge of the Counterfactual Consistency "
                "Score itself.")
    bullet(doc, "Replacement of rule-based strategy attribution with a "
                "learned attributor, conditional on obtaining labelled "
                "poisoning data from an independent source.")
    bullet(doc, "Evaluation across multiple cooperating gateways, where the "
                "counterfactual bank could be shared without sharing "
                "telemetry.")

    body(doc, "The framework as it stands establishes that counterfactual "
              "consequence is a usable and discriminating basis for deciding "
              "whether to accept a model update at the edge, and that the "
              "decision can be made on hardware a household already owns.")


# ===========================================================================
# Appendix A
# ===========================================================================
def appendix_a(doc):
    h1(doc, "Appendix A — Sample Code", bookmark_name="bm_appendix")

    body(doc, "The listings below are the two routines on which the "
              "framework's claim rests, reproduced from "
              "cihdt/counterfactual/validator.py.")

    h2(doc, "A.1  Scoring an Update Against Committed Futures")
    _code(doc, """shadow = self._shadow(update, core_X, core_y, core_dt)

shadow_pred = shadow.predict(bank.X, bank.dt)
inc_pred    = incumbent.predict(bank.X, bank.dt)
am, bm      = bank.attack_mask, bank.benign_mask

attack_agreement = float((shadow_pred[am] != NORMAL_IDX).mean())
benign_agreement = float((shadow_pred[bm] == NORMAL_IDX).mean())

caught     = inc_pred != NORMAL_IDX
downgraded = caught & (shadow_pred == NORMAL_IDX)
stability  = 1.0 - downgraded.sum() / caught.sum()

coherence, per_ratio, detail     = self._plane_coherence(update)
label_agreement, agree_detail    = self._label_agreement(update, incumbent)
tv, excess                       = self._label_shift(update)

directional     = tv if excess > 0 else min(tv, 0.35 * CFG.label_shift_full)
label_integrity = clip(1.0 - directional / CFG.label_shift_full, 0.0, 1.0)

ccs = (CFG.w_attack_agreement * attack_agreement
       + CFG.w_benign_agreement * benign_agreement
       + CFG.w_stability        * stability
       + CFG.w_plane_coherence  * coherence
       + CFG.w_label_integrity  * label_integrity
       + CFG.w_label_agreement  * label_agreement)""")

    h2(doc, "A.2  Calibrating the Accept Threshold")
    _code(doc, """scores = [self._score(u, bank, incumbent, core_X, core_y, core_dt)[0]
          for u in honest]
arr    = np.asarray(scores)

# The floor matters: calibration updates all come from one pool, so their
# measured spread understates what honest traffic varies by once the fleet
# drifts. Without it the gate lands inside the honest distribution.
spread = max(float(arr.std()), CFG.threshold_std_floor)
raw    = float(arr.mean() - CFG.threshold_z * spread)

self.threshold = float(np.clip(raw, CFG.threshold_floor,
                               CFG.threshold_ceiling))""")

    h2(doc, "A.3  The Decision, With Sybil Pressure Applied")
    _code(doc, """unseen           = update.source not in self.seen_sources
recent           = list(self.seen_sources)[-8:]
burst            = unseen and len(recent) >= 5 and len(set(recent)) >= 5
novelty_penalty  = 0.05 if burst else 0.0

effective = min(self.threshold + novelty_penalty, 0.97)
passed    = ccs >= effective and rep >= CFG.reputation_floor
decision  = (Decision.ACCEPTED.value if passed
             else Decision.QUARANTINED.value)""")


def _code(doc, text):
    """A monospaced listing."""
    from docx.shared import Pt
    for line in text.split("\n"):
        p = para(doc, line or " ", size=9.5, line=1.0, after=0)
        p.paragraph_format.left_indent = Pt(24)
        for run in p.runs:
            run.font.name = "Consolas"
    para(doc, "", size=9, after=10)
