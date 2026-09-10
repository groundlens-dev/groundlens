#![no_main]

// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The numeral grammar must never panic and must stay linear on hostile
//! input (the digit-group bound is what keeps it so).
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if let Ok(text) = std::str::from_utf8(data) {
        let text = gl_text::normalise(text);
        for name in ["und", "en", "es", "de", "fr", "ch"] {
            let profile = gl_numeric::locale(name).unwrap();
            let found = gl_numeric::find_bare_numerals(&text, &profile);
            for n in &found {
                assert!(n.span.end <= text.len());
                assert!(text.is_char_boundary(n.span.start) && text.is_char_boundary(n.span.end));
                assert!(!n.readings.is_empty());
            }
        }
    }
});
