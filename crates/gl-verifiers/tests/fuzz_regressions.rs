// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Regressions for crashes found by cargo-fuzz. Each test replays a minimised
//! crash input as a plain, deterministic unit test, so the fix is guarded on
//! every platform by `cargo test`, not only by the (non-deterministic) fuzz
//! job. A verifier must never panic on adversarial input; the worst it may do
//! is report "not comparable".
//!
//! Both inputs overflowed `Decimal` multiplication while converting a numeral
//! to its base unit: a huge magnitude paired with a scale word or a unit
//! factor. Fixed by making the conversion arithmetic checked in
//! `gl_numeric::quantity` (`find_quantities`, `Quantity::canonical`, `compare`).

use gl_core::{Source, VerificationInput, Verifier};

/// `quantities` target: `9…9 trillones` (long-scale word, 10^18) overflowed
/// when the numeral was multiplied by the scale in `find_quantities`.
#[test]
fn quantities_scale_word_overflow_does_not_panic() {
    let data: &[u8] = &[
        56, 56, 56, 46, 82, 56, 55, 56, 49, 49, 46, 56, 52, 56, 56, 56, 56, 116, 114, 105, 108, 108, 111,
        110, 101, 115,
    ];
    let text = gl_text::normalise(std::str::from_utf8(data).unwrap());
    for name in ["und", "en", "es", "fr"] {
        let profile = gl_numeric::locale(name).unwrap();
        let qs = gl_numeric::find_quantities(&text, &profile);
        for (i, a) in qs.iter().enumerate() {
            assert!(text.is_char_boundary(a.span.start) && text.is_char_boundary(a.span.end));
            let _ = a.canonical_text();
            for b in &qs[i..] {
                let _ = gl_numeric::compare(a, b, gl_numeric::MatchOptions::default());
            }
        }
    }
}

/// `numeric_verifier` target: a long run of `9`s ending in `MWh` overflowed
/// when the reading was converted to the base energy unit during `compare`.
#[test]
fn numeric_verifier_unit_conversion_overflow_does_not_panic() {
    let data: &[u8] = &[
        48, 56, 74, 0, 48, 49, 56, 74, 17, 57, 57, 57, 57, 57, 57, 57, 57, 57, 57, 56, 74, 17, 57, 57, 57,
        57, 57, 57, 57, 57, 57, 57, 57, 57, 57, 53, 57, 57, 57, 57, 57, 53, 57, 57, 56, 57, 57, 57, 57, 57,
        57, 57, 57, 57, 52, 49, 57, 48, 49, 77, 87, 104,
    ];
    let text = std::str::from_utf8(data).unwrap();
    let mut cut = text.len() / 2;
    while !text.is_char_boundary(cut) {
        cut += 1;
    }
    let (answer, source) = text.split_at(cut);
    let (answer, source) = (gl_text::normalise(answer), gl_text::normalise(source));
    let claims = gl_verifiers::extract_claims(&answer, "und");
    let input = VerificationInput {
        question: None,
        answer,
        sources: vec![Source { id: "s".into(), text: source, locator: None }],
        claims,
        locale: "und".into(),
        metadata: Default::default(),
    };
    let verifier = gl_verifiers::NumericVerifier::default();
    // The contract is simply: no panic.
    let _ = verifier.verify(&input);
}
