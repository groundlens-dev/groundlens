// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! `groundlens._engine`. Every function takes and returns plain strings
//! (JSON, YAML, hex) so the extension ABI is trivially stable and the Python
//! layer owns the ergonomics. No function here opens a network connection.

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;

fn err<E: std::fmt::Display>(e: E) -> PyErr {
    PyValueError::new_err(e.to_string())
}

/// Run a full verification. `request_json` is a `VerifyRequest`; the result
/// is a sealed `EvidenceRecord` as JSON.
#[pyfunction]
fn verify_json(request_json: &str) -> PyResult<String> {
    let req: gl_engine::VerifyRequest = serde_json::from_str(request_json).map_err(err)?;
    let record = gl_engine::verify(&req).map_err(err)?;
    serde_json::to_string(&record).map_err(err)
}

/// Like `verify_json`, returning `{"record": ..., "timings": ...}`. The
/// timings say how long each verifier took, in microseconds; they are not part
/// of the record.
#[pyfunction]
fn verify_timed_json(request_json: &str) -> PyResult<String> {
    let req: gl_engine::VerifyRequest = serde_json::from_str(request_json).map_err(err)?;
    let (record, timings) = gl_engine::verify_timed(&req).map_err(err)?;
    serde_json::to_string(&serde_json::json!({"record": record, "timings": timings})).map_err(err)
}

/// Like `verify_unsigned_json`, returning `{"record": ..., "timings": ...}`.
#[pyfunction]
fn verify_unsigned_timed_json(request_json: &str) -> PyResult<String> {
    let req: gl_engine::VerifyRequest = serde_json::from_str(request_json).map_err(err)?;
    let (record, timings) = gl_engine::verify_unsigned_timed(&req).map_err(err)?;
    serde_json::to_string(&serde_json::json!({"record": record, "timings": timings})).map_err(err)
}

/// Verify like `verify_json`, without signing: an `UnsignedRecord` as JSON.
/// A key service signs the UTF-8 bytes of its `record_hash`.
#[pyfunction]
fn verify_unsigned_json(request_json: &str) -> PyResult<String> {
    let req: gl_engine::VerifyRequest = serde_json::from_str(request_json).map_err(err)?;
    let unsigned = gl_engine::verify_unsigned(&req).map_err(err)?;
    serde_json::to_string(&unsigned).map_err(err)
}

/// The exact prompt a judge is sent for a request, as JSON: `system`,
/// `user`, `template_id`, `template_hash`, `prompt_hash`, `claims`.
#[pyfunction]
fn judge_prompt_json(request_json: &str) -> PyResult<String> {
    let req: gl_engine::VerifyRequest = serde_json::from_str(request_json).map_err(err)?;
    serde_json::to_string(&gl_engine::judge_prompt(&req).map_err(err)?).map_err(err)
}

/// Sign a document (a measurement or replay report) with a local Ed25519
/// seed. `content_json` is any JSON value; the result is a signed document.
#[pyfunction]
fn sign_document_json(kind: &str, content_json: &str, seed_hex: &str) -> PyResult<String> {
    let content: serde_json::Value = serde_json::from_str(content_json).map_err(err)?;
    let bytes: [u8; 32] = hex::decode(seed_hex)
        .ok()
        .and_then(|v| v.try_into().ok())
        .ok_or_else(|| PyValueError::new_err("signing key must be 32 bytes hex"))?;
    let doc =
        gl_record::sign_document(kind, content, &gl_record::RecordSigner::from_bytes(&bytes)).map_err(err)?;
    serde_json::to_string(&doc).map_err(err)
}

/// Check a signed document. Raises on a changed content or a bad signature.
#[pyfunction]
fn verify_document_json(doc_json: &str) -> PyResult<()> {
    let doc: gl_record::SignedDocument = serde_json::from_str(doc_json).map_err(err)?;
    gl_record::verify_document(&doc).map_err(|e| PyRuntimeError::new_err(e.to_string()))
}

/// Attach a key service's signature (hex) and public key (hex) to an unsigned
/// record. The signature is checked first; the result is a sealed record.
#[pyfunction]
fn attach_signature_json(
    unsigned_json: &str,
    algorithm: &str,
    public_key_hex: &str,
    signature_hex: &str,
) -> PyResult<String> {
    let unsigned: gl_record::UnsignedRecord = serde_json::from_str(unsigned_json).map_err(err)?;
    let public_key = hex::decode(public_key_hex).map_err(err)?;
    let signature = hex::decode(signature_hex).map_err(err)?;
    let record = gl_record::attach_signature(unsigned, algorithm, &public_key, &signature).map_err(err)?;
    serde_json::to_string(&record).map_err(err)
}

/// Verify several chains, each a JSON Lines text. Returns the record count;
/// raises on the first broken record or link, or a record in two chains.
#[pyfunction]
fn record_verify_chains(chains: Vec<String>) -> PyResult<usize> {
    let parsed: Vec<Vec<gl_record::EvidenceRecord>> =
        chains.iter().map(|c| gl_record::from_jsonl(c)).collect::<Result<_, _>>().map_err(err)?;
    gl_record::verify_chains(&parsed).map_err(|e| PyRuntimeError::new_err(e.to_string()))
}

/// Verify a whole MCP execution. `request_json` is a `RunVerifyRequest`; the
/// result is a sealed `RunRecord` as JSON. Its `content.gate` is the decision.
#[pyfunction]
fn run_verify_json(request_json: &str) -> PyResult<String> {
    let req: gl_engine::RunVerifyRequest = serde_json::from_str(request_json).map_err(err)?;
    let record = gl_engine::verify_run(&req).map_err(err)?;
    serde_json::to_string(&record).map_err(err)
}

/// Verify one run record or a whole JSON Lines chain of them. Returns the
/// number checked; raises on the first broken hash, link or signature.
#[pyfunction]
fn run_record_verify(jsonl: &str) -> PyResult<usize> {
    let records = gl_record::run_records_from_jsonl(jsonl).map_err(err)?;
    gl_record::verify_run_chain(&records).map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
    Ok(records.len())
}

/// Verify one record or a whole JSON Lines chain. Returns the number of
/// records checked; raises on the first broken hash, link or signature.
#[pyfunction]
fn record_verify(jsonl: &str) -> PyResult<usize> {
    let records = gl_record::from_jsonl(jsonl).map_err(err)?;
    gl_record::verify_chain(&records).map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
    Ok(records.len())
}

/// `(policy_hash, problems)`.
#[pyfunction]
fn policy_lint(yaml: &str) -> PyResult<(String, Vec<String>)> {
    gl_engine::policy_lint(yaml).map_err(err)
}

#[pyfunction]
fn default_policy_yaml() -> String {
    gl_engine::DEFAULT_POLICY_YAML.to_string()
}

/// The YAML of a shipped policy, by id; `None` when no such policy ships.
#[pyfunction]
fn builtin_policy_yaml(name: &str) -> Option<String> {
    gl_engine::gl_policy::builtin(name).map(str::to_string)
}

/// The resolved policy as YAML, headed by its id, version and hash.
#[pyfunction]
fn policy_resolve(yaml: &str) -> PyResult<String> {
    gl_engine::policy_resolve(yaml).map_err(err)
}

#[pyfunction]
fn keygen() -> String {
    gl_engine::keygen_hex()
}

#[pyfunction]
fn engine_version() -> String {
    gl_core::ENGINE_VERSION.to_string()
}

/// YAML → JSON, so the Python package needs no YAML dependency for rule sets.
#[pyfunction]
fn yaml_to_json(text: &str) -> PyResult<String> {
    let v: serde_yaml::Value = serde_yaml::from_str(text).map_err(err)?;
    serde_json::to_string(&v).map_err(err)
}

#[pymodule]
fn _engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(verify_json, m)?)?;
    m.add_function(wrap_pyfunction!(run_verify_json, m)?)?;
    m.add_function(wrap_pyfunction!(verify_unsigned_json, m)?)?;
    m.add_function(wrap_pyfunction!(verify_timed_json, m)?)?;
    m.add_function(wrap_pyfunction!(verify_unsigned_timed_json, m)?)?;
    m.add_function(wrap_pyfunction!(judge_prompt_json, m)?)?;
    m.add_function(wrap_pyfunction!(sign_document_json, m)?)?;
    m.add_function(wrap_pyfunction!(verify_document_json, m)?)?;
    m.add_function(wrap_pyfunction!(attach_signature_json, m)?)?;
    m.add_function(wrap_pyfunction!(record_verify_chains, m)?)?;
    m.add_function(wrap_pyfunction!(run_record_verify, m)?)?;
    m.add_function(wrap_pyfunction!(record_verify, m)?)?;
    m.add_function(wrap_pyfunction!(policy_lint, m)?)?;
    m.add_function(wrap_pyfunction!(default_policy_yaml, m)?)?;
    m.add_function(wrap_pyfunction!(builtin_policy_yaml, m)?)?;
    m.add_function(wrap_pyfunction!(policy_resolve, m)?)?;
    m.add_function(wrap_pyfunction!(keygen, m)?)?;
    m.add_function(wrap_pyfunction!(engine_version, m)?)?;
    m.add_function(wrap_pyfunction!(yaml_to_json, m)?)?;
    Ok(())
}
