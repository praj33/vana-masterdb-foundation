# -*- coding: utf-8 -*-
"""Validate the Group 3 observation fixtures against the frozen contract.

Proves two things Group 1 will care about:
  1. valid observations pass
  2. malformed ones are REJECTED, not silently accepted

Run:  python validate_fixtures.py
Needs: pip install jsonschema
"""
import json, io, sys, copy
from jsonschema import Draft202012Validator

SCHEMA = json.load(io.open("observation.schema.json", encoding="utf-8"))
PKG = json.load(io.open("sample_mission_package.json", encoding="utf-8"))
V = Draft202012Validator(SCHEMA)


def strip(o):
    return {k: v for k, v in o.items() if not k.startswith("_")}


def check(label, obs, expect_valid):
    errs = sorted(V.iter_errors(strip(obs)), key=lambda e: e.path)
    ok = (not errs) == expect_valid
    verdict = "PASS" if ok else "FAIL"
    want = "accept" if expect_valid else "REJECT"
    got = "accepted" if not errs else "rejected"
    print(f"  [{verdict}] {label:<46} expect {want:<7} got {got}")
    if errs and expect_valid:
        for e in errs[:3]:
            print(f"         ! {'/'.join(map(str, e.path)) or '<root>'}: {e.message[:90]}")
    if not errs and not expect_valid:
        print("         ! schema accepted a record it should have rejected")
    return ok


print("VALID OBSERVATIONS FROM THE MISSION PACKAGE")
results = []
for o in PKG["observations"]:
    results.append(check(o["observation_id"], o, True))

print()
print("MALFORMED OBSERVATIONS — must be rejected")
base = strip(PKG["observations"][0])

cases = []

o = copy.deepcopy(base); del o["timestamp"]
cases.append(("missing timestamp", o))

o = copy.deepcopy(base); del o["latitude"]
cases.append(("missing latitude", o))

o = copy.deepcopy(base); o["latitude"] = None
cases.append(("null location but quality_status VALIDATED", o))

o = copy.deepcopy(base); del o["device_id"]
cases.append(("missing device_id", o))

o = copy.deepcopy(base); o["observation_id"] = "OBS001"
cases.append(("observation_id is the bare sequence fragment", o))

o = copy.deepcopy(base); o["observation_id"] = "not-an-id"
cases.append(("malformed observation_id", o))

o = copy.deepcopy(base); o["measurement"] = 4.7; del o["unit"]
cases.append(("numeric measurement with no unit", o))

o = copy.deepcopy(base); o["accuracy"] = None
cases.append(("accuracy null instead of 'NOT VERIFIED'", o))

o = copy.deepcopy(base); o["accuracy"] = "approximately 5cm"
cases.append(("accuracy as free text", o))

o = copy.deepcopy(base); o["calibration_status"] = "probably fine"
cases.append(("calibration_status outside the enum", o))

o = copy.deepcopy(base); o["quality_status"] = "GOOD"
cases.append(("quality_status outside the enum", o))

o = copy.deepcopy(base); del o["raw_artifact_reference"]
cases.append(("missing raw artifact reference", o))

o = copy.deepcopy(base); del o["provenance"]
cases.append(("missing provenance", o))

o = copy.deepcopy(base); o["latitude"] = 191.3
cases.append(("latitude out of range", o))

o = copy.deepcopy(base); o["injected_field"] = "x"
cases.append(("unexpected extra field", o))

for label, obs in cases:
    results.append(check(label, obs, False))

print()
passed, total = sum(results), len(results)
print(f"{passed}/{total} checks passed")
if passed != total:
    sys.exit(1)
print()
print("A malformed or incomplete field observation cannot silently become a valid canonical record.")
