#![no_main]
//! Normalisation is idempotent and segmentation returns valid spans.
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if let Ok(text) = std::str::from_utf8(data) {
        let once = gl_text::normalise(text);
        assert_eq!(gl_text::normalise(&once), once, "normalise must be idempotent");
        for w in gl_text::words(&once, "en") {
            assert_eq!(&once[w.span.start..w.span.end], w.text);
        }
        let _ = gl_text::segmentation_warnings(&once);
    }
});
