# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""GroundLens Verification Conformance suite.

Does GroundLens do what it says? This runs canonical executions through the
engine and asserts the behaviours GroundLens promises, grouped by contract:

    Evidence generation   a verifier produced structured evidence with a span
    Policy semantics       the policy decides, not the verifier; regulation maps
    Decision determinism   same input, same content hash and signature
    Record integrity       a fresh record verifies; a chain links and verifies
    Tamper detection       an altered record is rejected
    Offline verification   verification needs no network
    Scope boundaries       only the given evidence is a source, never the question

The result is not a score. It is PASS or FAIL per contract. It uses only the
deterministic verifiers, so it needs no model bundle and no network:

    pip install groundlens
    python conformance.py            # human report, exit 1 if any FAIL
    python conformance.py --json     # machine-readable
"""

from __future__ import annotations

import json
import socket
import sys

from groundlens import Policy, Record, verify
from groundlens.record import IntegrityError

# A fixed 32-byte Ed25519 seed, so signatures are reproducible in the tests.
SEED = "00" * 31 + "01"
NO_LEX = dict(lexical=False)  # deterministic core only; no model bundle needed


def _checks_evidence():
    r = verify("Revenue was EUR 15M.", [("10k", "Revenue was EUR 10M.")], **NO_LEX)
    ev = r.evidence
    numeric = [e for e in ev if e.verifier_id == "groundlens.numeric"]
    spanned = [e for e in ev if isinstance(e.source_span, tuple) and len(e.source_span) == 2]
    yield "claim identified", len(r.claims) >= 1, f"{len(r.claims)} claim(s)"
    yield "numeric constraint checked", bool(numeric), f"{len(numeric)} numeric evidence item(s)"
    yield "source span recorded", bool(spanned), (f"span {spanned[0].source_span} -> {spanned[0].source_text!r}" if spanned else "no span")
    yield "verifier id + version recorded", bool(ev) and all(e.verifier_id and e.verifier_version for e in ev) and bool(r.verifiers), f"{len(r.verifiers)} verifier(s) declared"


def _checks_policy():
    default = verify("Revenue was EUR 15M.", [("10k", "Revenue was EUR 10M.")], **NO_LEX)
    permissive = Policy.from_yaml(
        "id: permissive\nversion: 1\nverifiers:\n  required: [groundlens.numeric]\n"
        "decision:\n  any_contradiction_from: []\n  unresolved_claims: REVIEW\n  tolerate_unresolved_kinds: [word]\n"
    )
    perm = verify("Revenue was EUR 15M.", [("10k", "Revenue was EUR 10M.")], policy=permissive, **NO_LEX)
    same_ev = [e.result for e in default.evidence] == [e.result for e in perm.evidence]
    yield "policy decides, not the verifier", same_ev and default.decision != perm.decision, f"same evidence -> {default.decision} vs {perm.decision}"
    yield "policy id + hash recorded", default.policy_id == "groundlens_default_v1" and bool(default.policy_hash), f"{default.policy_id} #{default.policy_hash[:12]}"
    eu = verify(
        "The invoice total is 1,000 dollars, due in 30 days.",
        [("invoice.pdf#p1", "The total amount due is 10,000 dollars, payable within 30 days.")],
        policy="eu_ai_act_high_risk_v1", question="What is the invoice total?", **NO_LEX)
    arts = [m.get("article") for m in eu.regulatory_mapping]
    yield "regulation mapped (EU AI Act)", eu.decision == "FAIL" and bool(arts) and all(arts), f"articles {arts}"


def _checks_determinism():
    a = verify("Total 1,000 dollars.", [("s", "Total 10,000 dollars.")], **NO_LEX)
    b = verify("Total 1,000 dollars.", [("s", "Total 10,000 dollars.")], **NO_LEX)
    k1 = verify("Total 1,000 dollars.", [("s", "Total 10,000 dollars.")], signing_key=SEED, **NO_LEX)
    k2 = verify("Total 1,000 dollars.", [("s", "Total 10,000 dollars.")], signing_key=SEED, **NO_LEX)
    # The content hash excludes the timestamp, so it is reproducible; the record hash
    # and signature include a fresh timestamp per record, so they are not, by design.
    # A fixed key gives a fixed signer identity, and both records verify.
    k1_ok = k2_ok = True
    try:
        k1.verify()
    except IntegrityError:
        k1_ok = False
    try:
        k2.verify()
    except IntegrityError:
        k2_ok = False
    yield "same input -> same content hash", a.content_hash == b.content_hash, a.content_hash[:16] + "..."
    yield "same input -> same decision", a.decision == b.decision, a.decision
    yield "fixed key -> same signer identity", k1.signer_public_key == k2.signer_public_key and k1_ok and k2_ok, "deterministic signer key; both verify"


def _checks_integrity():
    r = verify("Revenue was EUR 15M.", [("10k", "Revenue was EUR 10M.")], signing_key=SEED, **NO_LEX)
    ok_fresh = True
    try:
        r.verify()
    except IntegrityError:
        ok_fresh = False
    present = all([r.content_hash, r.record_hash, r.signature, r.signer_public_key])
    first = verify("A is 1.", [("s", "A is 1.")], signing_key=SEED, **NO_LEX)
    second = verify("B is 2.", [("s", "B is 2.")], signing_key=SEED, previous=first, **NO_LEX)
    linked = second.previous_record_hash == first.record_hash
    try:
        n = Record.verify_chain([first, second])
        chain_ok = linked and n == 2
    except IntegrityError:
        chain_ok = False
    yield "fresh record verifies", ok_fresh, "signature + hashes recompute"
    yield "integrity fields present", present, "content_hash, record_hash, signature, key"
    yield "chain links and verifies", chain_ok, f"prev_hash matches, {2} records verified"


def _tamper(r, mutate):
    d = json.loads(r.to_json())
    mutate(d)
    try:
        Record.from_json(json.dumps(d)).verify()
        return False  # should have raised
    except IntegrityError:
        return True


def _checks_tamper():
    r = verify("Revenue was EUR 15M.", [("10k", "Revenue was EUR 10M.")], signing_key=SEED, **NO_LEX)

    def flip_decision(d):
        d["content"]["outcome"]["decision"] = "PASS"

    def flip_signature(d):
        s = d["signature"]
        d["signature"] = ("f" if s[0] != "f" else "0") + s[1:]

    def flip_evidence(d):
        d["content"]["graph"]["evidence"][0]["score"] = 0.5

    yield "altered decision rejected", _tamper(r, flip_decision), "decision FAIL->PASS caught"
    yield "altered signature rejected", _tamper(r, flip_signature), "flipped signature byte caught"
    yield "altered evidence rejected", _tamper(r, flip_evidence), "changed score caught"


def _checks_offline():
    r = verify("Revenue was EUR 15M.", [("10k", "Revenue was EUR 10M.")], signing_key=SEED, **NO_LEX)
    saved = socket.socket

    def _blocked(*a, **k):
        raise OSError("network disabled for the conformance run")

    socket.socket = _blocked
    try:
        ok1 = True
        try:
            r.verify()
        except IntegrityError:
            ok1 = False
        try:
            Record.verify_chain([r])
            ok2 = True
        except IntegrityError:
            ok2 = False
    finally:
        socket.socket = saved
    yield "record verifies with no network", ok1, "sockets disabled"
    yield "chain verifies with no network", ok2, "sockets disabled"


def _checks_scope():
    given = {"10k"}
    r = verify("Revenue was EUR 15M.", [("10k", "Revenue was EUR 10M.")],
               question="What was revenue?", **NO_LEX)
    src = [e.source_id for e in r.evidence if e.source_id is not None]
    only_given = all(s in given for s in src)
    q_not_source = "What was revenue?" not in src
    yield "sources are only the given evidence", only_given, f"source_ids {sorted(set(src))}"
    yield "the question is not a source", q_not_source, "question accepted, not cited as evidence"


DIMENSIONS = [
    ("Evidence generation", _checks_evidence),
    ("Policy semantics", _checks_policy),
    ("Decision determinism", _checks_determinism),
    ("Record integrity", _checks_integrity),
    ("Tamper detection", _checks_tamper),
    ("Offline verification", _checks_offline),
    ("Scope boundaries", _checks_scope),
]


def run():
    results = []
    for name, fn in DIMENSIONS:
        checks = []
        try:
            for cname, ok, detail in fn():
                checks.append({"check": cname, "pass": bool(ok), "detail": detail})
        except Exception as e:  # a crash in a dimension is a FAIL, not a stack trace
            checks.append({"check": "dimension raised", "pass": False, "detail": repr(e)})
        results.append({"dimension": name, "pass": all(c["pass"] for c in checks), "checks": checks})
    return results


def main(argv):
    results = run()
    overall = all(d["pass"] for d in results)
    if "--json" in argv:
        print(json.dumps({"suite": "conformance", "pass": overall, "dimensions": results}, indent=2))
    else:
        print("GroundLens Verification Conformance\n")
        for d in results:
            print(f"{'PASS' if d['pass'] else 'FAIL'}  {d['dimension']}")
            for c in d["checks"]:
                mark = "  ok  " if c["pass"] else " FAIL "
                print(f"    [{mark}] {c['check']:<34} {c['detail']}")
            print()
        print(("ALL CONTRACTS PASS" if overall else "SOME CONTRACTS FAILED"))
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
