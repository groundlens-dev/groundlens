//! One serialisation, one hash.
//!
//! Every hash in a record is SHA-256 over canonical JSON: keys sorted,
//! no insignificant whitespace, UTF-8 preserved, floats printed by Rust's
//! shortest round-trip representation (which is platform independent) and
//! already quantised upstream. NaN and infinities are rejected.

use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::{Error, Result};

fn sort_value(value: Value) -> Result<Value> {
    Ok(match value {
        Value::Object(map) => {
            let mut entries: Vec<(String, Value)> = map.into_iter().collect();
            entries.sort_by(|a, b| a.0.cmp(&b.0));
            let mut out = serde_json::Map::new();
            for (k, v) in entries {
                out.insert(k, sort_value(v)?);
            }
            Value::Object(out)
        }
        Value::Array(items) => Value::Array(items.into_iter().map(sort_value).collect::<Result<Vec<_>>>()?),
        Value::Number(n) => {
            if let Some(f) = n.as_f64() {
                if !f.is_finite() {
                    return Err(Error::Serialisation("non-finite float in canonical JSON".into()));
                }
            }
            Value::Number(n)
        }
        other => other,
    })
}

/// Canonical JSON text of any serialisable value.
pub fn canonical_json<T: Serialize>(value: &T) -> Result<String> {
    let v = serde_json::to_value(value)?;
    let sorted = sort_value(v)?;
    Ok(serde_json::to_string(&sorted)?)
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hex::encode(hasher.finalize())
}

/// `sha256:<hex>` of the canonical JSON of `value`.
pub fn content_hash<T: Serialize>(value: &T) -> Result<String> {
    Ok(format!("sha256:{}", sha256_hex(canonical_json(value)?.as_bytes())))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::Serialize;

    #[derive(Serialize)]
    struct A {
        z: u8,
        a: Vec<f64>,
    }

    #[test]
    fn keys_are_sorted_and_output_is_compact() {
        let text = canonical_json(&A { z: 1, a: vec![0.5, 1.0] }).unwrap();
        assert_eq!(text, r#"{"a":[0.5,1.0],"z":1}"#);
    }

    #[test]
    fn hash_is_stable() {
        let h = content_hash(&A { z: 1, a: vec![] }).unwrap();
        assert!(h.starts_with("sha256:"));
        assert_eq!(h.len(), 7 + 64);
        assert_eq!(h, content_hash(&A { z: 1, a: vec![] }).unwrap());
    }
}
