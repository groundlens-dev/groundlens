#![no_main]

// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Policy YAML from an untrusted source must parse or fail cleanly, and a
//! parsed policy must lint and hash without panicking.
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if let Ok(text) = std::str::from_utf8(data) {
        if let Ok(policy) = gl_policy::Policy::from_yaml(text) {
            let _ = policy.hash();
            let _ = policy.lint(&[]);
        }
    }
});
