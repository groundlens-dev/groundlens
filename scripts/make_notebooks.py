# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Write the two example notebooks under examples/notebooks/.

Kept as a script so the notebooks can be regenerated without a notebook
editor and reviewed as plain text in pull requests.

    python scripts/make_notebooks.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "examples" / "notebooks"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": text.strip("\n").splitlines(keepends=True),
    }


def notebook(cells: list[dict]) -> dict:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "colab": {"provenance": []},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


# ---------------------------------------------------------------------------
# 01 · Verify an AI answer against its sources (EN · DE · FR · ES · IT)
# ---------------------------------------------------------------------------

NB1 = [
    md("""
# Verify an AI answer against its sources

**GroundLens** checks what an AI system says against the documents it was given, and keeps a record of that check that anyone can verify later.

This notebook takes one situation, an assistant answering a question about an invoice, in **English, German, French, Spanish and Italian**, and walks from `pip install` to a signed evidence record. You will see:

1. a wrong number caught in every language, whatever the number format;
2. what the evidence looks like, verifier by verifier;
3. the same evidence under two different policies, with two different decisions;
4. the record, its hash, and why it is the same on any machine.

Runs in Google Colab. Nothing here sends your text anywhere: the engine runs locally and never opens a network connection.
"""),
    md("""
## 1. Install

`pip install groundlens` installs the GroundLens engine (GLV, for GroundLens Verification): the numeric and rules verifiers, the policy engine, the signed records and the command line. No dependencies, no network.

The **base bundle** is an optional, explicit download (about 470 MB, once): the multilingual encoder that powers the lexical verifier. It is the only command in the package that touches the network, and the download is checked against a hash pinned in the engine.
"""),
    code("""
%pip install -q groundlens
!groundlens --version
"""),
    code("""
from groundlens import Bundle

bundle = Bundle.installed("base")
if bundle is None:
    try:
        bundle = Bundle.pull("base")          # ≈470 MB, a minute or two in Colab
    except Exception as e:                    # noqa: BLE001 - keep the notebook running without it
        print("base bundle not installed:", e)
        print("Continuing with the numeric and rules verifiers only.")
print(Bundle.status("base"))
"""),
    md("""
## 2. One situation, five languages

Same invoice, same question, same mistake: the assistant reads **ten thousand** as **one thousand**. Notice how differently the five languages write that number. GroundLens reads each one with the right locale and compares the quantities exactly, in base units.
"""),
    code("""
CASES = {
    "en": dict(
        question="What is the invoice total and when is it due?",
        source="The total amount due is 10,000 dollars, payable within 30 days of receipt.",
        answer="The invoice total is 1,000 dollars, due within 30 days of receipt.",
    ),
    "de": dict(
        question="Wie hoch ist der Rechnungsbetrag und wann ist er fällig?",
        source="Der Gesamtbetrag beläuft sich auf 10.000 Euro, zahlbar innerhalb von 30 Tagen nach Erhalt.",
        answer="Der Rechnungsbetrag beträgt 1.000 Euro, zahlbar innerhalb von 30 Tagen nach Erhalt.",
    ),
    "fr": dict(
        question="Quel est le montant de la facture et quand est-il dû ?",
        source="Le montant total s'élève à 10 000 euros, payable sous 30 jours à compter de la réception.",
        answer="Le montant de la facture est de 1 000 euros, payable sous 30 jours à compter de la réception.",
    ),
    "es": dict(
        question="¿Cuál es el importe de la factura y cuándo vence?",
        source="El importe total asciende a 10.000 euros, pagaderos en un plazo de 30 días desde la recepción.",
        answer="El importe de la factura es de 1.000 euros, pagaderos en un plazo de 30 días desde la recepción.",
    ),
    "it": dict(
        question="Qual è l'importo della fattura e quando scade?",
        source="L'importo totale ammonta a 10.000 euro, pagabili entro 30 giorni dal ricevimento.",
        answer="L'importo della fattura è di 1.000 euro, pagabili entro 30 giorni dal ricevimento.",
    ),
}
"""),
    code("""
from groundlens import verify

records = {}
for locale, case in CASES.items():
    records[locale] = verify(
        case["answer"],
        [("invoice.pdf#p1", case["source"])],
        question=case["question"],
        locale=locale,
    )
    print(f"[{locale}] {records[locale].decision}")
    print(records[locale].report())
    print()
"""),
    md("""
Five `FAIL`s, one reason each: the numeric verifier found the answer's amount nowhere in the source and tells you which source number it lost to. The `30` days are supported in every language, so they do not appear in the report; only what a reviewer needs to look at does.

## 3. The evidence, not the verdict

A record keeps everything each verifier said about each claim. A verifier never decides. Look at the Spanish case in full:
"""),
    code("""
r = records["es"]
print(f"{'verifier':<20} {'result':<13} {'score':>6}  {'nearest source text':<24} notes")
for e in r.evidence:
    print(f"{e.verifier_id:<20} {e.result:<13} {e.score:>6.2f}  {str(e.source_text):<24} {', '.join(e.notes)}")
"""),
    md("""
If the base bundle is installed you also see `groundlens.lexical` rows: one per content word, with the source word it is anchored to and a support score. Words like *importe* or *pagaderos* score high because the source says the same thing; the score is a contextual similarity from a frozen multilingual encoder, so the same word used differently scores lower, and the note `exact_string_in_span` tells you when the word is there verbatim anyway.

The 3.x API, `proofread()`, gives the same information as **receipts**: the weakest anchors first, each next to the source word it lost to.
"""),
    code("""
from groundlens import proofread

marks = proofread(CASES["fr"]["answer"], [("facture", CASES["fr"]["source"])], locale="fr", question=CASES["fr"]["question"], k=3)
print("floor:", round(marks.floor, 3), "| encoder:", marks.encoder_id)
print(marks.report())
for w in marks.warnings:
    print("warning:", w)
"""),
    md("""
## 4. A correct answer, and a paraphrase

Verification is not string matching. A paraphrase with the right numbers passes; the numbers are compared as quantities, so `1,2 km` in the answer and `1200 m` in the source agree, and so do `212 °F` and `100 °C`.
"""),
    code("""
ok = verify(
    "Die Leitung ist 1,2 km lang und der Siedepunkt liegt bei 212 °F; der Umsatz betrug 37,35 Milliarden Dollar.",
    [("bericht", "Länge der Leitung: 1200 m. Siedepunkt: 100 °C.\\nUmsatz (in Millionen Dollar)\\n2024   37.350")],
    locale="de",
)
print(ok.decision)
for e in ok.evidence:
    if e.verifier_id == "groundlens.numeric":
        print(f"  {e.result:<10} {e.rationale}")
"""),
    md("""
## 5. Policies decide

Which verifiers are required, what thresholds apply, what happens to a claim nobody could check: that is the **policy**, a short YAML file you control. The engine has no opinion. The same evidence under two policies can produce two decisions, and both are correct.

`eu_ai_act_high_risk_v1` ships with the package. It maps its outcomes to Art. 15(1) (accuracy and robustness) and Art. 12(1) (record keeping) of Regulation (EU) 2024/1689.
"""),
    code("""
from groundlens import Policy

case = CASES["it"]
strict = verify(case["answer"], [("fattura", case["source"])], question=case["question"], locale="it", policy="eu_ai_act_high_risk_v1")
print("eu_ai_act_high_risk_v1 →", strict.decision)
for m in strict.regulatory_mapping:
    print("   ", m["framework"], m["article"], "·", m["control"])

lenient = Policy.from_yaml('''
id: demo_review_only
version: 1.0.0
description: A numeric mismatch sends the answer to a human instead of failing it.
verifiers:
  required: [groundlens.numeric]
decision:
  any_contradiction_from: []
  unresolved_claims: REVIEW
  tolerate_unresolved_kinds: [word]
''')
review = verify(case["answer"], [("fattura", case["source"])], question=case["question"], locale="it", policy=lenient)
print("demo_review_only       →", review.decision)
print("same evidence?", [e.result for e in strict.evidence] == [e.result for e in review.evidence])
"""),
    md("""
## 6. The record

Every verification is sealed in a record: input hashes, the verifiers and model hashes that ran, the evidence, the policy and its hash, the decision, the regulatory mapping, an Ed25519 signature. `content_hash` covers everything that is a function of input, policy and bundle, so two runs of the same check give the same hash on any machine; the record id and timestamp stay outside it.
"""),
    code("""
again = verify(CASES["en"]["answer"], [("invoice.pdf#p1", CASES["en"]["source"])], question=CASES["en"]["question"], locale="en")
print("content_hash  ", records["en"].content_hash)
print("second run    ", again.content_hash, "(same)" if again.content_hash == records["en"].content_hash else "(different!)")
print("record ids    ", records["en"].record_id, again.record_id)
print("policy        ", records["en"].policy_id, records["en"].policy_hash[:23] + "…")
print("bundle        ", records["en"].bundle_hash)
records["en"].verify()   # recomputes every hash and the signature, offline; raises if anything was altered
print("signature verifies")
"""),
    code("""
# Append the five records to a log. Each one carries the hash of the previous one.
from pathlib import Path
from groundlens import Record

log = Path("records.jsonl")
log.unlink(missing_ok=True)
for locale, case in CASES.items():
    verify(case["answer"], [("invoice.pdf#p1", case["source"])], question=case["question"], locale=locale, log=log)
print(Record.verify_chain(Record.read_log(log)), "records, chain intact")
!groundlens record verify records.jsonl
"""),
    md("""
## Where next

* The second notebook, **Evidence records for auditors**, takes a log like this one and produces the report, the chain verification and the tamper test an auditor would run.
* Write your own policy with `Policy.from_yaml()` and your own rules (`rules=`) for the checks your domain needs.
* Documentation and source: [github.com/groundlens-dev/groundlens](https://github.com/groundlens-dev/groundlens).
"""),
]

# ---------------------------------------------------------------------------
# 02 · Evidence records for auditors
# ---------------------------------------------------------------------------

NB2 = [
    md("""
# Evidence records for auditors

A GroundLens verification does not end with `PASS` or `FAIL`. It ends with a **record**: a signed, hash-chained document that says which verifiers ran, what they measured, which policy interpreted the evidence, what was decided, and which regulatory controls that decision concerns.

This notebook shows the part of GroundLens an auditor, a compliance officer or a customer's risk team touches:

1. a log of verifications produced by an application;
2. verifying the whole chain offline: every hash, every link, every signature;
3. what happens when someone edits a record;
4. the mapping to the EU AI Act;
5. the report and the auditor's one-page guide that `groundlens report` produces.

Runs in Google Colab. The engine never opens a network connection.
"""),
    code("""
%pip install -q groundlens
!groundlens --version
"""),
    md("""
## 1. An application writes records

Imagine a document assistant answering questions about a loan agreement. Each answer is verified under the `eu_ai_act_high_risk_v1` policy and appended to a log. The application signs with its own key, so records can be attributed to it; here we generate one and keep it in an environment variable, which is how the command line picks it up too.
"""),
    code("""
import os, subprocess
from pathlib import Path
from groundlens import verify, Record

os.environ["GROUNDLENS_SIGNING_KEY"] = subprocess.run(["groundlens", "keygen"], capture_output=True, text=True).stdout.strip()
SIGNING_KEY = os.environ["GROUNDLENS_SIGNING_KEY"]

CONTRACT = [
    ("loan.pdf#p1", "Loan agreement. Principal: 250,000 euros. Annual percentage rate: 4.75%. Term: 240 months."),
    ("loan.pdf#p2", "Early repayment fee: 1.00% of the outstanding balance during the first 5 years, 0.50% thereafter."),
    ("loan.pdf#p3", "The borrower must hold a home insurance policy for the whole term. Payments are due on the 25th of each month."),
]

EXCHANGES = [
    ("What is the principal?", "The principal is 250,000 euros."),
    ("What is the APR?", "The annual percentage rate is 4.75%."),
    ("How long is the term?", "The term of the loan is 240 months."),
    ("What is the early repayment fee?", "Early repayment costs 1.00% of the outstanding balance in the first 5 years and 0.50% after that."),
    ("Is insurance required?", "Yes, a home insurance policy is required for the whole term."),
    ("What is the early repayment fee after year five?", "After the fifth year the fee is 0.75% of the outstanding balance."),
    ("When are payments due?", "Payments are due on the 15th of each month."),
]

log = Path("records.jsonl")
log.unlink(missing_ok=True)
for question, answer in EXCHANGES:
    r = verify(answer, CONTRACT, question=question, locale="en", policy="eu_ai_act_high_risk_v1", signing_key=SIGNING_KEY, log=log)
    print(f"{r.decision:<7} {question}")
"""),
    md("""
Two answers are wrong: the fee after year five (0.75 % instead of 0.50 %) and the payment day (15th instead of 25th). Both were caught by the exact numeric verifier, with the source number they lost to. The answer about insurance contains no numbers, so the numeric verifier has nothing to say about it; with the base bundle installed, the lexical verifier anchors its words in the sources and the policy's threshold on that score applies. Which claims may go unchecked, and what happens then, is written in the policy, not in the engine.

## 2. Verify the chain, offline

An auditor receives `records.jsonl` and nothing else. Verification recomputes every content hash, every record hash, every link to the previous record and every signature. It needs no key material from the application: the public key travels inside each record.
"""),
    code("""
records = Record.read_log(log)
print(Record.verify_chain(records), "records verified")
print()
print(f"{'record_id':<32} {'decision':<8} {'previous_record_hash':<26} signer")
for r in records:
    prev = (r.previous_record_hash or "—")[:23]
    print(f"{r.record_id:<32} {r.decision:<8} {prev:<26} {r.signer_public_key[:16]}…")
"""),
    code("""
# The same check from the command line, which is what an auditor without Python would run
# (the glv binary exposes the same command).
!groundlens record verify records.jsonl
"""),
    md("""
## 3. What happens when a record is edited

Turn one `FAIL` into a `PASS` by hand and verify again. The content hash no longer matches the content, so the record is rejected; and because every record carries the hash of the previous one, removing a record from the middle of the log breaks the chain too.
"""),
    code("""
import json
from groundlens.record import IntegrityError

lines = log.read_text(encoding="utf-8").splitlines()
tampered = json.loads(lines[-1])
tampered["content"]["outcome"]["decision"] = "PASS"
try:
    Record.from_json(json.dumps(tampered)).verify()
except IntegrityError as e:
    print("edited record rejected:", str(e)[:120])

try:
    Record.verify_chain([Record.from_json(l) for l in lines[:3] + lines[4:]])
except IntegrityError as e:
    print("record removed from the log, chain rejected:", str(e)[:120])
"""),
    md("""
## 4. The regulatory mapping

The policy, not the engine, says what a decision means for compliance. `eu_ai_act_high_risk_v1` maps `FAIL` and `REVIEW` outcomes to Art. 15(1) (accuracy, robustness) and Art. 12(1) (record keeping) of Regulation (EU) 2024/1689. The mapping is inside each record, next to the decision it applies to, and the policy hash guarantees it is the mapping that was in force at the time.
"""),
    code("""
for r in records:
    if r.regulatory_mapping:
        print(r.decision, r.record_id)
        for m in r.regulatory_mapping:
            print(f"   {m['framework']}  {m['article']}  {m['control']}")
        for reason in r.reasons:
            print("   →", reason)
print()
print("policy:", records[0].policy_id, records[0].policy_hash)
"""),
    md("""
## 5. The report

`groundlens report` turns a log into the files an auditor actually reads: `report.md` (decisions, reasons, verifiers, policy and bundle hashes), `report.json` (the same, for tooling), the `records.jsonl` copy it was built from, and `README-auditor.md`, a one-page explanation of how to verify the package independently.
"""),
    code("""
!groundlens report records.jsonl --out evidence-package
print(open("evidence-package/report.md", encoding="utf-8").read())
"""),
    code("""
print(open("evidence-package/README-auditor.md", encoding="utf-8").read())
"""),
    md("""
## What an auditor can rely on

* **Integrity**: any change to a record, or to the order of the log, is detected offline by anyone with the file.
* **Attribution**: each record is signed; the public key is in the record.
* **Reproducibility**: the same input, policy and bundle give the same content hash on any machine. Exact verifiers are bit-identical; statistical verifiers run pinned models with declared tolerances and guard bands, so a platform difference can never flip a decision.
* **Separation of duties**: the engine measured, the policy decided, and the policy is named and hashed in every record. Whoever wrote the policy owns the decision rule.

Source and documentation: [github.com/groundlens-dev/groundlens](https://github.com/groundlens-dev/groundlens).
"""),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "01_verify_an_answer_in_five_languages.ipynb").write_text(json.dumps(notebook(NB1), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "02_evidence_records_for_auditors.ipynb").write_text(json.dumps(notebook(NB2), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
