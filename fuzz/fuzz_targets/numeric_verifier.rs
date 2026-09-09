#![no_main]
//! The whole exact channel: extract claims from one half of the input,
//! verify against the other half. Must never panic; evidence spans must
//! index the normalised texts.
use gl_core::{Source, VerificationInput, Verifier};
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    let Ok(text) = std::str::from_utf8(data) else { return };
    // Split on a char boundary: the harness must never be the thing that panics.
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
    if let Ok(evidence) = verifier.verify(&input) {
        for e in evidence {
            assert!(input.claim(&e.claim_id).is_some());
            if let Some(span) = e.receipt.source_span {
                let src = &input.sources[0].text;
                assert!(span.end <= src.len() && src.is_char_boundary(span.start) && src.is_char_boundary(span.end));
            }
        }
    }
});
