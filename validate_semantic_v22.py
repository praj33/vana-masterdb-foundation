# -*- coding: utf-8 -*-
"""V2.2 semantic / referential validation — the layer JSON Schema cannot provide.

WHY THIS FILE EXISTS
--------------------
The V2.2 schema tells consumers that cross-field agreement "is enforced by
contract/validate_semantic_v22.py". Until 2026-08-20 that file did not exist —
the contract described enforcement that was not implemented. An adversarial
audit found that a record whose provenance pointed at a different device, a
different mission and a different artifact validated cleanly.

This closes that. Checks 2-5 are Manya Shukla's original design, carried forward
from the V1.2 semantic layer and extended for V2.2's new fields.

WHAT JSON SCHEMA STRUCTURALLY CANNOT DO
---------------------------------------
Schema validates SHAPE. It cannot compare two fields to each other, and it
cannot check a reference against a register. An observation can be perfectly
schema-valid while claiming device G3-LIDAR-001 at the top level and
G3-CAM-001 in its provenance — internally contradictory, and its provenance
therefore worthless.

Run:  python validate_semantic_v22.py
"""
import copy, io, json, sys
from datetime import datetime


def ts(v):
    """Parse an ISO-8601 UTC timestamp to an instant.

    Timestamps MUST be compared as instants, never as strings. Arya's metadata
    contract section 6 permits fractional seconds, and '+00:00' and 'Z' are both
    valid UTC designators - so three spellings of the SAME instant are legal:

        2026-08-13T09:14:22Z
        2026-08-13T09:14:22+00:00
        2026-08-13T09:14:22.172677Z

    Under string comparison '09:14:22Z' > '09:14:22.172677Z' (because 'Z' sorts
    after '.'), and '...Z' != '...+00:00'. An earlier version of this file
    compared strings, so it reported a source_timestamp as being AFTER the
    observation when the two named the same second, and reported provenance
    captured_at as disagreeing with observation_timestamp when both were the
    same instant written two legal ways. Found by audit 2026-08-20.
    """
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def _load_json(filename):
    p = BASE_DIR / filename
    if not p.exists():
        p = BASE_DIR / filename.replace(".v2.2", "")
    if not p.exists():
        p = BASE_DIR / "observation.schema.json"
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

SCHEMA = _load_json("observation.schema.v2.2.json")
PKG = _load_json("sample_mission_package.v2.2.json")

KNOWN_DEVICES = {o["device_id"] for o in PKG.get("observations", []) if "device_id" in o}
KNOWN_DEVICES.update({"G3-SENSOR-999", "G3-LIDAR-001", "G3-CAM-001", "G3-CAM-002", "LIDAR-UNIT-02", "CAM-UNIT-01"})

# Arya's compatibility table, from her V2.2 contract section 4.
SYNTHETIC_MAP = {
    "PHYSICAL":   (False,),
    "CONTROLLED": (True,),
    "SYNTHETIC":  (True,),
    "SIMULATED":  (True,),
    "UNKNOWN":    (None,),
}


def strip(o):
    return {k: v for k, v in o.items() if not k.startswith("_")}


def semantic_errors(o):
    """Return agreement/reference failures. Empty list = passes."""
    errs = []
    prov = o.get("provenance") or {}
    loc = o.get("location") or {}
    integ = o.get("raw_artifact_integrity") or {}
    m = o.get("measurement")

    # --- 1. device must be known to the register [stand-in]
    dev_id = o.get("device_id")
    if dev_id not in KNOWN_DEVICES and not (isinstance(dev_id, str) and dev_id.startswith("G3-EXT-")):
        errs.append("device_id %r not in the device register (stand-in: fixture device set)"
                    % dev_id)

    # --- 2. provenance device must agree with the observation device   [Manya]
    if prov.get("device_id") != o.get("device_id"):
        errs.append("provenance.device_id %r disagrees with device_id %r"
                    % (prov.get("device_id"), o.get("device_id")))

    # --- 3. provenance mission must agree with the top-level mission   [Manya]
    if prov.get("mission_id") != o.get("mission_id"):
        errs.append("provenance.mission_id %r disagrees with mission_id %r"
                    % (prov.get("mission_id"), o.get("mission_id")))

    # --- 4. raw artifact must be traceable through provenance          [Manya]
    if not prov.get("raw_artifact"):
        errs.append("provenance.raw_artifact missing - provenance links Device -> Operator -> Mission "
                    "-> Raw Artifact and the last link is absent")
    elif prov["raw_artifact"] != o.get("raw_artifact"):
        errs.append("provenance.raw_artifact %r disagrees with raw_artifact %r"
                    % (prov.get("raw_artifact"), o.get("raw_artifact")))

    # --- 5. capture time must agree                                    [Manya]
    if prov.get("captured_at") and ts(prov["captured_at"]) != ts(o.get("observation_timestamp")):
        errs.append("provenance.captured_at %r disagrees with observation_timestamp %r"
                    % (prov.get("captured_at"), o.get("observation_timestamp")))

    # --- 6. the composite ID must agree with its own component fields
    parts = (o.get("observation_id") or "").split("-")
    if len(parts) >= 5:
        for f, expected in (("survey_id", parts[0]), ("zone_id", parts[1]),
                            ("flight_id", parts[2]), ("sensor_id", parts[3]),
                            ("observation_seq", parts[4])):
            if f in o and o[f] != expected:
                errs.append("%s %r contradicts observation_id component %r"
                            % (f, o[f], expected))

    # --- 7. a source_timestamp may not post-date the observation
    st, ot = ts(o.get("source_timestamp")), ts(o.get("observation_timestamp"))
    if st and ot and st > ot:
        errs.append("source_timestamp %r is AFTER observation_timestamp %r - a source cannot "
                    "report a reading later than the observation it produced" % (st, ot))

    # --- 8. Arya's compatibility mapping, enforced in full
    ss, isyn = o.get("synthetic_state"), o.get("is_synthetic")
    if ss in SYNTHETIC_MAP and "is_synthetic" in o:
        allowed = SYNTHETIC_MAP[ss] + (None,)
        if isyn not in allowed:
            errs.append("synthetic_state %s maps to is_synthetic %r in Arya's table, got %r"
                        % (ss, SYNTHETIC_MAP[ss][0], isyn))

    # --- 9. PHYSICAL requires real hardware evidence, not just a flag
    if ss == "PHYSICAL":
        if o.get("hardware_verified") is not True:
            errs.append("synthetic_state PHYSICAL requires hardware_verified true")
        if not integ.get("checksum_sha256"):
            errs.append("synthetic_state PHYSICAL requires a real content hash - a physical "
                        "capture must hash the evidence it produced")

    # --- 10. data_state and quality_state must not contradict
    #     RULED by Arya Barge 2026-08-20: "They are two distinct required axes.
    #     data_state represents lifecycle/data state; quality_state represents QA/quality
    #     verdict. We retain both fields and reject outright contradictions. They must not
    #     be merged or treated as aliases." The owner kept the identical vocabulary for
    #     both, so only outright contradictions are detectable - that is the ruled design.
    ds, qs = o.get("data_state"), o.get("quality_state")
    CONTRADICTORY = {("VALIDATED", "REJECTED"), ("REJECTED", "VALIDATED"),
                     ("INGESTED", "REJECTED"), ("REJECTED", "INGESTED")}
    if (ds, qs) in CONTRADICTORY:
        errs.append("data_state %s contradicts quality_state %s - a record cannot be both"
                    % (ds, qs))

    # --- 11. a null position must be paired with UNCERTAIN in quality_state
    if loc.get("latitude") is None or loc.get("longitude") is None:
        if o.get("quality_state") != "UNCERTAIN":
            errs.append("null coordinate without quality_state UNCERTAIN")

    # --- 12. provenance_reference must actually point somewhere
    pr = o.get("provenance_reference")
    if not pr or not str(pr).strip():
        errs.append("provenance_reference missing or empty")

    # --- 13. accuracy must never be invented                   [metadata contract s9]
    #     "Accuracy shall contain either a verified numeric value; or NOT VERIFIED.
    #      No plausible-looking estimate shall be invented."
    #     Controlled Observation Fixtures rules 4 and 6: no GPS accuracy shall be
    #     invented; unsupported accuracy shall be recorded as NOT VERIFIED.
    acc = o.get("accuracy")
    if isinstance(acc, (int, float)) and not isinstance(acc, bool):
        if o.get("hardware_verified") is not True:
            errs.append("accuracy %r is a numeric figure but hardware_verified is not true - an "
                        "accuracy value with no verified hardware behind it is invented. Use the "
                        "literal 'NOT_VERIFIED'" % acc)

    # --- 14. the same rule for position accuracy               [fixtures rule 4]
    pa = loc.get("position_accuracy_m")
    if isinstance(pa, (int, float)) and not isinstance(pa, bool):
        if o.get("hardware_verified") is not True:
            errs.append("location.position_accuracy_m %r asserted without verified hardware - "
                        "no GPS accuracy shall be invented" % pa)

    # --- 15. calibration must not be claimed without evidence  [metadata contract s10]
    #     "No calibration record shall be claimed without evidence."
    if o.get("calibration_state") == "CALIBRATED" and o.get("hardware_verified") is not True:
        errs.append("calibration_state CALIBRATED claimed with hardware_verified %r - no calibration "
                    "record shall be claimed without evidence" % o.get("hardware_verified"))

    # --- 16. an untrusted clock must be declared               [metadata contract s6]
    #     "If the clock cannot be trusted, the system shall not invent a timestamp."
    #     A null captured_at is that admission; it must show in the data state.
    if "captured_at" in prov and prov.get("captured_at") is None:
        if o.get("data_state") != "UNCERTAIN":
            errs.append("provenance.captured_at is null (clock not trusted) but data_state is %r, "
                        "not UNCERTAIN" % o.get("data_state"))

    # --- 17. tidal state must not be invented                  [metadata contract s14]
    #     "No tidal state shall be invented." A definite reading needs a named source.
    tid = o.get("tidal_state")
    if isinstance(tid, dict) and tid.get("state") not in (None, "UNKNOWN"):
        if not (tid.get("source") or "").strip():
            errs.append("tidal_state %r asserted with no source - no tidal state shall be invented; "
                        "record UNKNOWN instead" % tid.get("state"))
    elif isinstance(tid, str) and tid != "UNKNOWN":
        errs.append("tidal_state %r given as a bare string carries no source. The object form with a "
                    "named source is required for a definite reading" % tid)

    # --- 18. the idempotency key derives from the identity     [metadata contract s16]
    ik = o.get("idempotency_key")
    if ik and o.get("observation_id") and o["observation_id"] not in ik:
        errs.append("idempotency_key %r is not derived from observation_id %r - a repeated submission "
                    "would create a second canonical record" % (ik, o["observation_id"]))

    # --- 19. external_api requires flight_id EXT, flight_id EXT requires external_api, G3-EXT-* requires external_api, and external_api cannot be PHYSICAL
    cm = o.get("capture_method")
    fl = o.get("flight_id")
    ss = o.get("synthetic_state")
    if cm == "external_api" and fl != "EXT":
        errs.append("capture_method external_api requires flight_id EXT, got %r" % fl)
    if fl == "EXT" and cm != "external_api":
        errs.append("flight_id EXT requires capture_method external_api, got %r" % cm)
    if isinstance(dev_id, str) and dev_id.startswith("G3-EXT-") and cm != "external_api":
        errs.append("device_id %r starts with G3-EXT- and requires capture_method external_api, got %r" % (dev_id, cm))
    if cm == "external_api" and ss == "PHYSICAL":
        errs.append("capture_method external_api cannot carry synthetic_state PHYSICAL")

    return errs


res = []


def check(label, obs, expect_pass):
    e = semantic_errors(strip(obs))
    ok = (not e) == expect_pass
    print("  [%s] %-56s expect %-6s got %s"
          % ("PASS" if ok else "FAIL", label,
             "accept" if expect_pass else "REJECT",
             "accepted" if not e else "rejected"))
    if e and expect_pass:
        for x in e[:2]:
            print("         ! %s" % x[:100])
    if not e and not expect_pass:
        print("         ! a contradictory record was accepted")
    return ok


def run_semantic_suite():
    res = []
    print("V2.2 SEMANTIC / REFERENTIAL VALIDATION")
    print("agreement between fields - which JSON Schema structurally cannot express")
    print()
    print("VALID OBSERVATIONS")
    for o in PKG["observations"]:
        res.append(check(o["observation_id"], o, True))

    base = strip(PKG["observations"][0])
    print()
    print("CONTRADICTORY RECORDS - must be rejected")
    for label, mut in [
        ("device not in register",          lambda o: o.__setitem__("device_id", "DEV-UNKNOWN-999")),
        ("provenance device disagrees",     lambda o: o["provenance"].__setitem__("device_id", "G3-CAM-001")),
        ("provenance mission disagrees",    lambda o: o["provenance"].__setitem__("mission_id", "OTHER-MISSION")),
        ("provenance artifact disagrees",   lambda o: o["provenance"].__setitem__("raw_artifact", "other.las")),
        ("provenance captured_at disagrees",lambda o: o["provenance"].__setitem__("captured_at", "2026-08-13T11:00:00Z")),
        ("zone_id contradicts composite ID",lambda o: o.__setitem__("zone_id", "Z07")),
        ("sensor_id contradicts composite ID", lambda o: o.__setitem__("sensor_id", "IMX500")),
        ("source_timestamp after observation", lambda o: o.__setitem__("source_timestamp", "2027-01-01T00:00:00Z")),
        ("captured_at a different instant",  lambda o: o["provenance"].__setitem__("captured_at", "2026-08-13T09:14:23Z")),
        ("empty provenance_reference",      lambda o: o.__setitem__("provenance_reference", "   ")),
    ]:
        o = copy.deepcopy(base); mut(o)
        res.append(check(label, o, False))

    print()
    print("TIMESTAMPS COMPARED AS INSTANTS, NOT STRINGS - three legal spellings of one instant")
    for label, mut, exp in [
        ("captured_at '+00:00' vs observation 'Z' (same instant)",
         lambda o: o["provenance"].__setitem__("captured_at", "2026-08-13T09:14:22+00:00"), True),
        ("source '...22Z' vs observation '...22.172677Z' (same second)",
         lambda o: (o.__setitem__("observation_timestamp", "2026-08-13T09:14:22.172677Z"),
                    o["provenance"].__setitem__("captured_at", "2026-08-13T09:14:22.172677Z")), True),
        ("source genuinely one second later - still rejected",
         lambda o: o.__setitem__("source_timestamp", "2026-08-13T09:14:23Z"), False),
    ]:
        obs = copy.deepcopy(base); mut(obs)
        res.append(check(label, obs, exp))

    print()
    print("ARYA'S FROZEN METADATA CONTRACT - RULES THAT FORBID INVENTION")
    for label, mut, exp in [
        ("accuracy numeric without verified hardware",
         lambda o: o.__setitem__("accuracy", 0.85), False),
        ("accuracy NOT_VERIFIED (the honest form)",
         lambda o: o.__setitem__("accuracy", "NOT_VERIFIED"), True),
        ("position_accuracy_m asserted without hardware",
         lambda o: o["location"].__setitem__("position_accuracy_m", 1.5), False),
        ("calibration CALIBRATED without evidence",
         lambda o: o.__setitem__("calibration_state", "CALIBRATED"), False),
        ("null captured_at without data_state UNCERTAIN",
         lambda o: o["provenance"].__setitem__("captured_at", None), False),
        ("provenance.raw_artifact missing",
         lambda o: o["provenance"].__setitem__("raw_artifact", None), False),
        ("tidal_state HIGH with no source",
         lambda o: o.__setitem__("tidal_state", {"state": "HIGH", "source": None}), False),
        ("tidal_state HIGH with a named source",
         lambda o: o.__setitem__("tidal_state", {"state": "HIGH", "source": "INCOIS tide table"}), True),
        ("idempotency_key not derived from the identity",
         lambda o: o.__setitem__("idempotency_key", "some-random-uuid"), False),
    ]:
        obs = copy.deepcopy(base); mut(obs)
        res.append(check(label, obs, exp))

    print()
    print("ARYA'S COMPATIBILITY TABLE - enforced in both directions")
    for label, mut, exp in [
        ("SYNTHETIC + is_synthetic false",
         lambda o: o.__setitem__("is_synthetic", False), False),
        ("PHYSICAL + is_synthetic true",
         lambda o: (o.__setitem__("synthetic_state", "PHYSICAL"), o.__setitem__("is_synthetic", True)), False),
        ("CONTROLLED + is_synthetic true (correct)",
         lambda o: o.__setitem__("synthetic_state", "CONTROLLED"), True),
        ("UNKNOWN + is_synthetic null (correct)",
         lambda o: (o.__setitem__("synthetic_state", "UNKNOWN"), o.__setitem__("is_synthetic", None)), True),
    ]:
        o = copy.deepcopy(base); mut(o)
        res.append(check(label, o, exp))

    print()
    print("PHYSICAL REQUIRES EVIDENCE, NOT A FLAG")
    o = copy.deepcopy(base)
    o["synthetic_state"] = "PHYSICAL"; o["is_synthetic"] = False
    res.append(check("PHYSICAL without hardware_verified", o, False))
    o["hardware_verified"] = True
    o["raw_artifact_integrity"] = {"checksum_sha256": None, "hash_algorithm": None, "artifact_type": "point_cloud"}
    res.append(check("PHYSICAL, verified, but no content hash", o, False))
    o["raw_artifact_integrity"]["checksum_sha256"] = "a" * 63 + "f"
    o["raw_artifact_integrity"]["hash_algorithm"] = "sha256"
    res.append(check("PHYSICAL, verified, hashed (a real capture)", o, True))

    print()
    print("STATE CONTRADICTION")
    for label, ds, qs in [("data_state VALIDATED vs quality_state REJECTED", "VALIDATED", "REJECTED"),
                          ("data_state REJECTED vs quality_state VALIDATED", "REJECTED", "VALIDATED")]:
        o = copy.deepcopy(base); o["data_state"] = ds; o["quality_state"] = qs
        res.append(check(label, o, False))

    print()
    print("V2.2 EXTERNAL-API / EXT CROSS-FIELD SEMANTIC RULES")
    for label, mut, exp in [
        ("valid EXT + external_api observation",
         lambda o: (o.__setitem__("observation_id", "TC-Z03-EXT-OPENMETEO-OBS001"),
                    o.__setitem__("flight_id", "EXT"),
                    o.__setitem__("sensor_id", "OPENMETEO"),
                    o.__setitem__("capture_method", "external_api"),
                    o.__setitem__("device_id", "G3-EXT-OPENMETEO-01"),
                    o.__setitem__("mission_id", "TC-Z03-EXT"),
                    o["provenance"].__setitem__("device_id", "G3-EXT-OPENMETEO-01"),
                    o["provenance"].__setitem__("mission_id", "TC-Z03-EXT"),
                    o.__setitem__("idempotency_key", "IK-TC-Z03-EXT-OPENMETEO-OBS001")), True),
        ("external_api + flight_id F001 (rejected)",
         lambda o: (o.__setitem__("observation_id", "TC-Z03-F001-OPENMETEO-OBS001"),
                    o.__setitem__("flight_id", "F001"),
                    o.__setitem__("capture_method", "external_api"),
                    o.__setitem__("device_id", "G3-EXT-OPENMETEO-01"),
                    o.__setitem__("mission_id", "TC-Z03-F001"),
                    o["provenance"].__setitem__("device_id", "G3-EXT-OPENMETEO-01"),
                    o["provenance"].__setitem__("mission_id", "TC-Z03-F001"),
                    o.__setitem__("idempotency_key", "IK-TC-Z03-F001-OPENMETEO-OBS001")), False),
        ("EXT + capture_method sensor (rejected)",
         lambda o: (o.__setitem__("observation_id", "TC-Z03-EXT-OPENMETEO-OBS001"),
                    o.__setitem__("flight_id", "EXT"),
                    o.__setitem__("capture_method", "sensor"),
                    o.__setitem__("idempotency_key", "IK-TC-Z03-EXT-OPENMETEO-OBS001")), False),
        ("G3-EXT-* device + capture_method sensor (rejected)",
         lambda o: (o.__setitem__("device_id", "G3-EXT-OPENMETEO-01"),
                    o["provenance"].__setitem__("device_id", "G3-EXT-OPENMETEO-01"),
                    o.__setitem__("capture_method", "sensor")), False),
        ("external_api + synthetic_state PHYSICAL (rejected)",
         lambda o: (o.__setitem__("observation_id", "TC-Z03-EXT-OPENMETEO-OBS001"),
                    o.__setitem__("flight_id", "EXT"),
                    o.__setitem__("capture_method", "external_api"),
                    o.__setitem__("device_id", "G3-EXT-OPENMETEO-01"),
                    o.__setitem__("mission_id", "TC-Z03-EXT"),
                    o["provenance"].__setitem__("device_id", "G3-EXT-OPENMETEO-01"),
                    o["provenance"].__setitem__("mission_id", "TC-Z03-EXT"),
                    o.__setitem__("synthetic_state", "PHYSICAL"),
                    o.__setitem__("is_synthetic", False),
                    o.__setitem__("hardware_verified", True),
                    o.__setitem__("raw_artifact_integrity", {"checksum_sha256": "a"*64, "hash_algorithm": "sha256", "artifact_type": "other"}),
                    o.__setitem__("idempotency_key", "IK-TC-Z03-EXT-OPENMETEO-OBS001")), False),
    ]:
        o = copy.deepcopy(base); mut(o)
        res.append(check(label, o, exp))

    print()
    print("=" * 78)
    print("%d/%d semantic checks passed" % (sum(1 for r in res if r), len(res)))
    print()
    print("KNOWN LIMITATIONS, stated rather than hidden:")
    print("  - KNOWN_DEVICES is a STAND-IN. No device register service exists; Group 4's")
    print("    capability registry is file-based and holds only a placeholder for Group 3.")
    print("  - data_state / quality_state were RULED two distinct required axes by the contract")
    print("    owner on 2026-08-20, with the IDENTICAL vocabulary retained for both. Only outright")
    print("    contradictions are therefore detectable. That is the ruled design, not a gap.")
    print("  - synthetic_state PHYSICAL is currently unreachable for real Group 3 data: no")
    print("    sensor has produced a recorded reading and 0 of 8 actuators are mounted.")
    return all(res)


if __name__ == "__main__":
    success = run_semantic_suite()
    sys.exit(0 if success else 1)
