#!/usr/bin/env python3
"""End-to-end check against the real encoder. Run this on a machine with a model.

The test suite runs entirely against a deterministic fake encoder, which is the
right default -- it means CI is fast, offline, and tests the library rather than
a checkpoint. But it cannot tell you whether the real tokenizer's offsets line
up with our spans, or whether a genuine 400-token answer survives windowing.

    pip install "groundlens[encoder]"
    python scripts/verify_encoder.py

Exit code 0 means every check passed. Anything else, read the output.
"""

from __future__ import annotations

import sys

from groundlens import score
from groundlens._numerals import locale
from groundlens._words import segment

CONTEXT = (
    "According to the invoice, the total amount due is 10,000 dollars, "
    "payable within 30 days of delivery to the client's warehouse."
)
GROUNDED = (
    "The document is an invoice describing the commercial terms of the delivery. "
    "It specifies the payment schedule, notes that payment is expected within 30 days "
    "of delivery, and states a total amount due of 10,000 dollars for the goods received, "
    "consistent with the agreed terms."
)
PERTURBED = GROUNDED.replace("10,000", "1,000")
REFORMATTED = GROUNDED.replace("10,000", "10000")

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not condition:
        failures.append(name)


def main() -> int:
    from groundlens import SentenceTransformerEncoder

    print("loading encoder...")
    encoder = SentenceTransformerEncoder()
    print(f"  id         {encoder.id}")
    print(f"  max_tokens {encoder.max_tokens}")
    if encoder.id.endswith("@unresolved"):
        print("  NOTE: revision could not be resolved from the Hub. Any hash produced")
        print("        here is not pinned to a checkpoint. Pass revision= explicitly")
        print("        before publishing a number.")

    print("\ninvoice fixture")
    profiles = {
        name: score(text, [("invoice.pdf#p1", CONTEXT)], encoder=encoder, k=1)
        for name, text in (
            ("grounded", GROUNDED),
            ("perturbed", PERTURBED),
            ("reformatted", REFORMATTED),
        )
    }
    for name, profile in profiles.items():
        print(f"  {name:12s} score={profile.score:.3f}  {profile.report()}")

    check(
        "a wrong number collapses the score",
        profiles["perturbed"].score < profiles["grounded"].score,
        f"{profiles['perturbed'].score:.3f} < {profiles['grounded'].score:.3f}",
    )
    check(
        "the weakest anchor IS the wrong number",
        profiles["perturbed"].weakest[0].text == "1,000",
        repr(profiles["perturbed"].weakest[0].text),
    )
    check(
        "the receipt names the source number",
        profiles["perturbed"].weakest[0].evidence_text == "10,000",
        repr(profiles["perturbed"].weakest[0].evidence_text),
    )
    check(
        "reformatting is not a defect",
        abs(profiles["reformatted"].score - profiles["grounded"].score) < 1e-6,
    )

    print("\nthe geometry channel cannot see the digit (this is the point)")
    geo = {
        name: score(text, [("c", CONTEXT)], encoder=encoder, k=4)
        for name, text in (("grounded", GROUNDED), ("perturbed", PERTURBED))
    }
    lexical = {
        name: sorted(a.support for a in p.anchors if a.kind == "lexical")[:4]
        for name, p in geo.items()
    }
    delta = abs(sum(lexical["grounded"]) - sum(lexical["perturbed"])) / 4
    print(f"  mean of 4 weakest LEXICAL anchors moves by {delta:.4f} when the number is wrong")
    check("pure geometry is near-blind to the digit", delta < 0.05, f"{delta:.4f} < 0.05")

    print("\nwindowing on a long answer")
    long_answer = " ".join([GROUNDED] * 12)
    profile = score(long_answer, [("c", CONTEXT)], encoder=encoder, k=1, max_anchors=8192)
    expected = len([u for u in segment(long_answer, locale("und")) if u.kind != "skipped"])
    token_count = len(encoder.token_spans(long_answer))
    print(f"  {token_count} tokens across windows of {encoder.max_tokens}")
    check(
        "no scoring word dropped past the token cap",
        profile.n_scored == expected,
        f"{profile.n_scored} == {expected}",
    )
    check("the long answer actually exceeded one window", token_count > encoder.max_tokens)

    print("\ndeterminism of the real path")
    a = score(GROUNDED, [("c", CONTEXT)], encoder=encoder, k=1)
    b = score(GROUNDED, [("c", CONTEXT)], encoder=encoder, k=1)
    check("same input, same hash", a.profile_sha256 == b.profile_sha256)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all checks passed")
    print(f"encoder_id for the record: {encoder.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
