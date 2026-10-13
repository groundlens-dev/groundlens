// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The evidence record. One per verification. Hash-chained to the previous
//! one, signed with Ed25519, appended to a JSON Lines log that is never
//! rewritten.
//!
//! What the record proves: which verifiers ran (with artefact hashes), what
//! evidence they produced, which policy interpreted it (by hash), what
//! configuration produced the decision, and that nothing was altered or
//! removed afterwards. The timestamp and the record id are *outside* the
//! content hash, so two runs of the same input on two machines produce the
//! same `content_hash` while still being two distinct records.
//!
//! ## Who signs
//!
//! A record is signed with Ed25519 by default, from a key the engine holds.
//! A key that must never leave a key service (AWS KMS, Azure Key Vault, an
//! HSM through PKCS#11) signs from outside the engine instead: the engine
//! builds an [`UnsignedRecord`], the key service signs its `record_hash`, and
//! [`attach_signature`] checks that signature before it accepts the record.
//! Those services sign with ECDSA on P-256, so a record carries a
//! `signature_algorithm`; a record without one is Ed25519, as every record
//! written before the field existed.

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier as _, VerifyingKey};
use gl_core::canonical::{canonical_json, content_hash, sha256_hex};
use gl_core::{Error, EvidenceGraph, Result, VerificationInput};
use gl_policy::PolicyOutcome;
use serde::{Deserialize, Serialize};

pub mod run;
pub use run::{
    run_record_to_jsonl_line, run_records_from_jsonl, seal_run, verify_run_against_record, verify_run_chain,
    verify_run_record, RunRecord, RunRecordContent, RUN_RECORD_SCHEMA,
};

pub const RECORD_SCHEMA: &str = "groundlens.evidence-record/1";

/// The default signature: Ed25519 over the bytes of `record_hash`.
pub const ED25519: &str = "ed25519";
/// ECDSA on P-256 with SHA-256 over the bytes of `record_hash`. The public key
/// is stored as an uncompressed SEC1 point and the signature as `r || s`,
/// both hex.
pub const ECDSA_P256_SHA256: &str = "ecdsa-p256-sha256";

/// Everything that is a function of the input, the bundle and the policy.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecordContent {
    pub schema: String,
    pub engine_version: String,
    pub bundle_hash: String,
    pub input_hash: String,
    pub locale: String,
    pub graph: EvidenceGraph,
    pub outcome: PolicyOutcome,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EvidenceRecord {
    pub record_id: String,
    pub timestamp: String,
    pub content: RecordContent,
    /// `sha256:` of the canonical JSON of `content`.
    pub content_hash: String,
    pub previous_record_hash: Option<String>,
    /// `sha256:` over `content_hash || previous_record_hash || record_id || timestamp`.
    pub record_hash: String,
    /// Over the bytes of `record_hash`, hex, under `signature_algorithm`.
    pub signature: String,
    pub signer_public_key: String,
    /// `ecdsa-p256-sha256` for a record signed by a key service. Absent means
    /// Ed25519, so records written before this field keep verifying and keep
    /// their exact bytes.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub signature_algorithm: Option<String>,
}

/// A record with every hash computed and no signature yet: what a key
/// service is asked to sign. Sign the UTF-8 bytes of `record_hash`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnsignedRecord {
    pub record_id: String,
    pub timestamp: String,
    pub content: RecordContent,
    pub content_hash: String,
    pub previous_record_hash: Option<String>,
    pub record_hash: String,
}

pub struct RecordSigner {
    key: SigningKey,
}

impl RecordSigner {
    pub fn generate() -> Self {
        RecordSigner { key: SigningKey::generate(&mut rand_core::OsRng) }
    }

    pub fn from_bytes(bytes: &[u8; 32]) -> Self {
        RecordSigner { key: SigningKey::from_bytes(bytes) }
    }

    pub fn public_key_hex(&self) -> String {
        hex::encode(self.key.verifying_key().to_bytes())
    }

    /// The private seed, hex. Store it in a secret manager, never in the bundle.
    pub fn seed_hex(&self) -> String {
        hex::encode(self.key.to_bytes())
    }
}

pub fn input_hash(input: &VerificationInput) -> Result<String> {
    content_hash(input)
}

pub(crate) fn chain_hash(
    content_hash: &str,
    previous: Option<&str>,
    record_id: &str,
    timestamp: &str,
) -> String {
    let material = format!("{content_hash}\n{}\n{record_id}\n{timestamp}", previous.unwrap_or(""));
    format!("sha256:{}", sha256_hex(material.as_bytes()))
}

/// The signed, hash-chained envelope around a content hash. Independent of what
/// the content is, so an answer record and a run record share exactly the same
/// signing and chaining. Returns `(record_hash, signature_hex, public_key_hex)`.
pub(crate) fn sign_envelope(
    content_hash: &str,
    previous: Option<&str>,
    record_id: &str,
    timestamp: &str,
    signer: &RecordSigner,
) -> (String, String, String) {
    let record_hash = chain_hash(content_hash, previous, record_id, timestamp);
    let signature = signer.key.sign(record_hash.as_bytes());
    (record_hash, hex::encode(signature.to_bytes()), signer.public_key_hex())
}

/// Recompute the envelope and check the signature, given a freshly recomputed
/// content hash. The single place both record kinds verify.
#[allow(clippy::too_many_arguments)]
pub(crate) fn verify_envelope(
    recomputed_content_hash: &str,
    stored_content_hash: &str,
    previous: Option<&str>,
    record_id: &str,
    timestamp: &str,
    stored_record_hash: &str,
    signature_hex: &str,
    signer_public_key: &str,
    algorithm: Option<&str>,
) -> Result<()> {
    if recomputed_content_hash != stored_content_hash {
        return Err(Error::Integrity(format!("{record_id}: content hash mismatch")));
    }
    let expected = chain_hash(stored_content_hash, previous, record_id, timestamp);
    if expected != stored_record_hash {
        return Err(Error::Integrity(format!("{record_id}: record hash mismatch")));
    }
    match algorithm.unwrap_or(ED25519) {
        ED25519 => {}
        ECDSA_P256_SHA256 => {
            return verify_p256(stored_record_hash, signature_hex, signer_public_key)
                .map_err(|e| Error::Integrity(format!("{record_id}: {e}")));
        }
        other => return Err(Error::Integrity(format!("{record_id}: unknown signature algorithm {other:?}"))),
    }
    let pk_bytes: [u8; 32] = hex::decode(signer_public_key)
        .ok()
        .and_then(|v| v.try_into().ok())
        .ok_or_else(|| Error::Integrity("bad public key".into()))?;
    let pk = VerifyingKey::from_bytes(&pk_bytes).map_err(|e| Error::Integrity(e.to_string()))?;
    let sig_bytes: [u8; 64] = hex::decode(signature_hex)
        .ok()
        .and_then(|v| v.try_into().ok())
        .ok_or_else(|| Error::Integrity("bad signature encoding".into()))?;
    let sig = Signature::from_bytes(&sig_bytes);
    pk.verify(stored_record_hash.as_bytes(), &sig)
        .map_err(|_| Error::Integrity(format!("{record_id}: signature does not verify")))
}

fn verify_p256(
    record_hash: &str,
    signature_hex: &str,
    public_key_hex: &str,
) -> std::result::Result<(), String> {
    use p256::ecdsa::signature::Verifier as _;
    let key_bytes = hex::decode(public_key_hex).map_err(|_| "bad public key encoding".to_string())?;
    let key = p256::ecdsa::VerifyingKey::from_sec1_bytes(&key_bytes)
        .map_err(|_| "bad P-256 public key".to_string())?;
    let sig_bytes = hex::decode(signature_hex).map_err(|_| "bad signature encoding".to_string())?;
    let sig =
        p256::ecdsa::Signature::from_slice(&sig_bytes).map_err(|_| "bad P-256 signature".to_string())?;
    key.verify(record_hash.as_bytes(), &sig).map_err(|_| "signature does not verify".to_string())
}

/// Bring a P-256 public key to the stored form, uncompressed SEC1 hex.
/// Accepts SEC1 (compressed or not) or a DER SubjectPublicKeyInfo, which is
/// what AWS KMS `GetPublicKey` returns.
pub fn normalise_p256_public_key(bytes: &[u8]) -> Result<String> {
    use p256::pkcs8::DecodePublicKey as _;
    let key = p256::PublicKey::from_sec1_bytes(bytes)
        .or_else(|_| p256::PublicKey::from_public_key_der(bytes))
        .map_err(|_| {
            Error::InvalidInput("not a P-256 public key (SEC1 or SubjectPublicKeyInfo DER)".into())
        })?;
    Ok(hex::encode(p256::EncodedPoint::from(key).as_bytes()))
}

/// Bring a P-256 signature to the stored form, `r || s` hex with a low `s`.
/// Accepts `r || s` (Azure Key Vault, PKCS#11) or DER (AWS KMS).
pub fn normalise_p256_signature(bytes: &[u8]) -> Result<String> {
    let sig = p256::ecdsa::Signature::from_slice(bytes)
        .or_else(|_| p256::ecdsa::Signature::from_der(bytes))
        .map_err(|_| Error::InvalidInput("not a P-256 ECDSA signature (r||s or DER)".into()))?;
    let sig = sig.normalize_s().unwrap_or(sig);
    Ok(hex::encode(sig.to_bytes()))
}

/// Compute every hash of a record and leave the signature to a key service.
pub fn prepare_unsigned(
    content: RecordContent,
    previous_record_hash: Option<String>,
    record_id: String,
    timestamp: String,
) -> Result<UnsignedRecord> {
    let content_hash = content_hash(&content)?;
    let record_hash = chain_hash(&content_hash, previous_record_hash.as_deref(), &record_id, &timestamp);
    Ok(UnsignedRecord { record_id, timestamp, content, content_hash, previous_record_hash, record_hash })
}

/// Attach a key service's signature to an unsigned record. The signature is
/// checked before the record is returned, so a record that comes out of here
/// always verifies. `public_key` and `signature` are raw bytes, in any of the
/// encodings [`normalise_p256_public_key`] and [`normalise_p256_signature`]
/// accept for `ecdsa-p256-sha256`, or 32 and 64 bytes for `ed25519`.
pub fn attach_signature(
    unsigned: UnsignedRecord,
    algorithm: &str,
    public_key: &[u8],
    signature: &[u8],
) -> Result<EvidenceRecord> {
    let (signer_public_key, signature, signature_algorithm) = match algorithm {
        ED25519 => (hex::encode(public_key), hex::encode(signature), None),
        ECDSA_P256_SHA256 => (
            normalise_p256_public_key(public_key)?,
            normalise_p256_signature(signature)?,
            Some(ECDSA_P256_SHA256.to_string()),
        ),
        other => return Err(Error::InvalidInput(format!("unknown signature algorithm {other:?}"))),
    };
    let record = EvidenceRecord {
        record_id: unsigned.record_id,
        timestamp: unsigned.timestamp,
        content: unsigned.content,
        content_hash: unsigned.content_hash,
        previous_record_hash: unsigned.previous_record_hash,
        record_hash: unsigned.record_hash,
        signature,
        signer_public_key,
        signature_algorithm,
    };
    verify_record(&record)
        .map_err(|e| Error::InvalidInput(format!("the key service's signature was refused: {e}")))?;
    Ok(record)
}

pub fn seal(
    content: RecordContent,
    previous_record_hash: Option<String>,
    record_id: String,
    timestamp: String,
    signer: &RecordSigner,
) -> Result<EvidenceRecord> {
    let content_hash = content_hash(&content)?;
    let (record_hash, signature, signer_public_key) =
        sign_envelope(&content_hash, previous_record_hash.as_deref(), &record_id, &timestamp, signer);
    Ok(EvidenceRecord {
        record_id,
        timestamp,
        content,
        content_hash,
        previous_record_hash,
        record_hash,
        signature,
        signer_public_key,
        signature_algorithm: None,
    })
}

/// Recompute every hash and check the signature of one record.
pub fn verify_record(record: &EvidenceRecord) -> Result<()> {
    let recomputed = content_hash(&record.content)?;
    verify_envelope(
        &recomputed,
        &record.content_hash,
        record.previous_record_hash.as_deref(),
        &record.record_id,
        &record.timestamp,
        &record.record_hash,
        &record.signature,
        &record.signer_public_key,
        record.signature_algorithm.as_deref(),
    )
}

/// Verify a whole log: every record individually, and every link.
pub fn verify_chain(records: &[EvidenceRecord]) -> Result<()> {
    let mut previous: Option<&str> = None;
    for r in records {
        verify_record(r)?;
        if r.previous_record_hash.as_deref() != previous {
            return Err(Error::Integrity(format!("{}: broken chain link", r.record_id)));
        }
        previous = Some(&r.record_hash);
    }
    Ok(())
}

/// A signed document that is not a verification: a measurement report, a
/// replay report. Same hashing and Ed25519 signature as a record, without the
/// chain. `kind` names the document schema.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignedDocument {
    pub kind: String,
    pub content: serde_json::Value,
    /// `sha256:` of the canonical JSON of `kind` and `content`.
    pub content_hash: String,
    /// Ed25519 over the bytes of `content_hash`, hex.
    pub signature: String,
    pub signer_public_key: String,
}

#[derive(Serialize)]
struct DocumentBody<'a> {
    kind: &'a str,
    content: &'a serde_json::Value,
}

/// Sign a document with a local key.
pub fn sign_document(
    kind: &str,
    content: serde_json::Value,
    signer: &RecordSigner,
) -> Result<SignedDocument> {
    let content_hash = content_hash(&DocumentBody { kind, content: &content })?;
    let signature = hex::encode(signer.key.sign(content_hash.as_bytes()).to_bytes());
    Ok(SignedDocument {
        kind: kind.to_string(),
        content,
        content_hash,
        signature,
        signer_public_key: signer.public_key_hex(),
    })
}

/// Recompute the hash of a signed document and check its signature.
pub fn verify_document(doc: &SignedDocument) -> Result<()> {
    let recomputed = content_hash(&DocumentBody { kind: &doc.kind, content: &doc.content })?;
    if recomputed != doc.content_hash {
        return Err(Error::Integrity(format!("{}: content hash mismatch", doc.kind)));
    }
    let pk_bytes: [u8; 32] = hex::decode(&doc.signer_public_key)
        .ok()
        .and_then(|v| v.try_into().ok())
        .ok_or_else(|| Error::Integrity("bad public key".into()))?;
    let pk = VerifyingKey::from_bytes(&pk_bytes).map_err(|e| Error::Integrity(e.to_string()))?;
    let sig_bytes: [u8; 64] = hex::decode(&doc.signature)
        .ok()
        .and_then(|v| v.try_into().ok())
        .ok_or_else(|| Error::Integrity("bad signature encoding".into()))?;
    pk.verify(doc.content_hash.as_bytes(), &Signature::from_bytes(&sig_bytes))
        .map_err(|_| Error::Integrity(format!("{}: signature does not verify", doc.kind)))
}

/// Verify a set of chains, each one a log written by one writer. Many
/// processes may each keep their own chain; every chain must verify on its
/// own, and no record may appear in two of them. Returns the record count.
pub fn verify_chains(chains: &[Vec<EvidenceRecord>]) -> Result<usize> {
    let mut seen = std::collections::BTreeSet::new();
    let mut total = 0;
    for chain in chains {
        verify_chain(chain)?;
        for r in chain {
            if !seen.insert(r.record_hash.clone()) {
                return Err(Error::Integrity(format!("{}: the same record is in two chains", r.record_id)));
            }
        }
        total += chain.len();
    }
    Ok(total)
}

pub fn to_jsonl_line(record: &EvidenceRecord) -> Result<String> {
    canonical_json(record)
}

pub fn from_jsonl(text: &str) -> Result<Vec<EvidenceRecord>> {
    text.lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| serde_json::from_str(l).map_err(Error::from))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use gl_policy::{Decision, PolicyOutcome};

    fn content(n: u8) -> RecordContent {
        RecordContent {
            schema: RECORD_SCHEMA.into(),
            engine_version: "0.1.0".into(),
            bundle_hash: "sha256:bundle".into(),
            input_hash: format!("sha256:input{n}"),
            locale: "en".into(),
            graph: EvidenceGraph::default(),
            outcome: PolicyOutcome {
                policy_id: "p".into(),
                policy_version: "1".into(),
                policy_hash: "sha256:p".into(),
                decision: Decision::Pass,
                claims: vec![],
                missing_required: vec![],
                excluded_verifiers: vec![],
                regulatory_mapping: vec![],
                reasons: vec![],
                risk_class: None,
                pass_means: None,
            },
        }
    }

    #[test]
    fn chain_verifies_and_tampering_is_detected() {
        let signer = RecordSigner::generate();
        let r1 = seal(content(1), None, "r1".into(), "2026-09-07T10:00:00Z".into(), &signer).unwrap();
        let r2 = seal(
            content(2),
            Some(r1.record_hash.clone()),
            "r2".into(),
            "2026-09-07T10:00:01Z".into(),
            &signer,
        )
        .unwrap();
        verify_chain(&[r1.clone(), r2.clone()]).unwrap();

        let mut tampered = r1.clone();
        tampered.content.outcome.decision = Decision::Fail;
        assert!(verify_record(&tampered).is_err());
        assert!(verify_chain(&[r2.clone(), r1.clone()]).is_err());

        let line = to_jsonl_line(&r1).unwrap();
        let back = from_jsonl(&line).unwrap();
        verify_record(&back[0]).unwrap();
    }

    #[test]
    fn a_key_service_signs_with_p256_and_the_record_verifies() {
        use p256::ecdsa::signature::Signer as _;
        use p256::pkcs8::EncodePublicKey as _;
        let key = p256::ecdsa::SigningKey::from_slice(&[7u8; 32]).unwrap();
        let unsigned =
            prepare_unsigned(content(1), None, "k1".into(), "2026-10-13T10:00:00Z".into()).unwrap();
        // What AWS KMS returns: a DER signature and a DER SubjectPublicKeyInfo.
        let sig: p256::ecdsa::Signature = key.sign(unsigned.record_hash.as_bytes());
        let der_sig = sig.to_der();
        let spki = p256::PublicKey::from(key.verifying_key()).to_public_key_der().unwrap();
        let record =
            attach_signature(unsigned.clone(), ECDSA_P256_SHA256, spki.as_bytes(), der_sig.as_bytes())
                .unwrap();
        assert_eq!(record.signature_algorithm.as_deref(), Some(ECDSA_P256_SHA256));
        assert_eq!(record.signature.len(), 128, "r || s, hex");
        assert_eq!(record.signer_public_key.len(), 130, "uncompressed SEC1, hex");
        verify_record(&record).unwrap();
        let back = from_jsonl(&to_jsonl_line(&record).unwrap()).unwrap();
        verify_record(&back[0]).unwrap();

        // What Azure Key Vault and PKCS#11 return: raw r || s.
        let raw = attach_signature(
            unsigned.clone(),
            ECDSA_P256_SHA256,
            key.verifying_key().to_encoded_point(true).as_bytes(),
            &sig.to_bytes(),
        )
        .unwrap();
        assert_eq!(raw.signature, record.signature);

        // A signature over anything else is refused before a record exists.
        let wrong: p256::ecdsa::Signature = key.sign(b"something else");
        let e =
            attach_signature(unsigned, ECDSA_P256_SHA256, spki.as_bytes(), &wrong.to_bytes()).unwrap_err();
        assert!(e.to_string().contains("refused"), "{e}");

        // A relabelled algorithm does not verify.
        let mut relabelled = record.clone();
        relabelled.signature_algorithm = None;
        assert!(verify_record(&relabelled).is_err());
    }

    #[test]
    fn a_signed_document_verifies_and_any_change_is_caught() {
        let signer = RecordSigner::generate();
        let doc = sign_document("groundlens.measurement/1", serde_json::json!({"n": 50}), &signer).unwrap();
        verify_document(&doc).unwrap();
        let mut changed = doc.clone();
        changed.content = serde_json::json!({"n": 51});
        assert!(verify_document(&changed).is_err());
        let mut relabelled = doc;
        relabelled.kind = "groundlens.replay/1".into();
        assert!(verify_document(&relabelled).is_err());
    }

    #[test]
    fn an_ed25519_record_has_no_algorithm_field_and_keeps_its_bytes() {
        let signer = RecordSigner::generate();
        let r = seal(content(1), None, "e".into(), "2026-01-01T00:00:00Z".into(), &signer).unwrap();
        assert!(!to_jsonl_line(&r).unwrap().contains("signature_algorithm"));
    }

    #[test]
    fn several_chains_verify_together_and_a_record_in_two_chains_does_not() {
        let signer = RecordSigner::generate();
        let a = seal(content(1), None, "a".into(), "2026-01-01T00:00:00Z".into(), &signer).unwrap();
        let b = seal(content(2), None, "b".into(), "2026-01-01T00:00:00Z".into(), &signer).unwrap();
        assert_eq!(verify_chains(&[vec![a.clone()], vec![b]]).unwrap(), 2);
        assert!(verify_chains(&[vec![a.clone()], vec![a]]).is_err());
    }

    #[test]
    fn content_hash_is_independent_of_time_and_id() {
        let signer = RecordSigner::generate();
        let a = seal(content(1), None, "a".into(), "2026-01-01T00:00:00Z".into(), &signer).unwrap();
        let b = seal(content(1), None, "b".into(), "2027-01-01T00:00:00Z".into(), &signer).unwrap();
        assert_eq!(a.content_hash, b.content_hash);
        assert_ne!(a.record_hash, b.record_hash);
    }
}
