#![no_main]
//! Quantities: scale words, currencies, percent, physical units, headers.
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if let Ok(text) = std::str::from_utf8(data) {
        let text = gl_text::normalise(text);
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
});
