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

/// Normalise and extract claims without running verifiers.
#[pyfunction]
fn prepare_json(request_json: &str) -> PyResult<String> {
    let req: gl_engine::VerifyRequest = serde_json::from_str(request_json).map_err(err)?;
    serde_json::to_string(&gl_engine::prepare(&req)).map_err(err)
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

#[pyfunction]
fn keygen() -> String {
    gl_engine::keygen_hex()
}

#[pyfunction]
fn engine_version() -> String {
    gl_core::ENGINE_VERSION.to_string()
}

#[pyfunction]
fn normalise(text: &str) -> String {
    gl_text::normalise(text)
}

/// Build `manifest.json` for a bundle directory. Returns the manifest hash.
#[pyfunction]
fn bundle_build(root: &str, name: &str, version: &str) -> PyResult<String> {
    let manifest =
        gl_bundle::build_manifest(std::path::Path::new(root), name, version, gl_core::ENGINE_VERSION)
            .map_err(err)?;
    let text = serde_json::to_string_pretty(&manifest).map_err(err)?;
    std::fs::write(std::path::Path::new(root).join("manifest.json"), text).map_err(err)?;
    manifest.hash().map_err(err)
}

/// `(name, version, manifest_hash)`; raises if any artefact hash mismatches.
#[pyfunction]
fn bundle_verify(root: &str) -> PyResult<(String, String, String)> {
    let b = gl_bundle::Bundle::open(root).map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
    Ok((b.manifest.name, b.manifest.version, b.manifest_hash))
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
    m.add_function(wrap_pyfunction!(prepare_json, m)?)?;
    m.add_function(wrap_pyfunction!(record_verify, m)?)?;
    m.add_function(wrap_pyfunction!(policy_lint, m)?)?;
    m.add_function(wrap_pyfunction!(default_policy_yaml, m)?)?;
    m.add_function(wrap_pyfunction!(keygen, m)?)?;
    m.add_function(wrap_pyfunction!(engine_version, m)?)?;
    m.add_function(wrap_pyfunction!(normalise, m)?)?;
    m.add_function(wrap_pyfunction!(bundle_build, m)?)?;
    m.add_function(wrap_pyfunction!(bundle_verify, m)?)?;
    m.add_function(wrap_pyfunction!(yaml_to_json, m)?)?;
    Ok(())
}
