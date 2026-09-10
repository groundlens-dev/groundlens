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

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier as _, VerifyingKey};
use gl_core::canonical::{canonical_json, content_hash, sha256_hex};
use gl_core::{Error, EvidenceGraph, Result, VerificationInput};
use gl_policy::PolicyOutcome;
use serde::{Deserialize, Serialize};

pub const RECORD_SCHEMA: &str = "groundlens.evidence-record/1";

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
    /// Ed25519 over `record_hash`, hex.
    pub signature: String,
    pub signer_public_key: String,
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

fn chain_hash(content_hash: &str, previous: Option<&str>, record_id: &str, timestamp: &str) -> String {
    let material = format!("{content_hash}\n{}\n{record_id}\n{timestamp}", previous.unwrap_or(""));
    format!("sha256:{}", sha256_hex(material.as_bytes()))
}

pub fn seal(
    content: RecordContent,
    previous_record_hash: Option<String>,
    record_id: String,
    timestamp: String,
    signer: &RecordSigner,
) -> Result<EvidenceRecord> {
    let content_hash = content_hash(&content)?;
    let record_hash = chain_hash(&content_hash, previous_record_hash.as_deref(), &record_id, &timestamp);
    let signature = signer.key.sign(record_hash.as_bytes());
    Ok(EvidenceRecord {
        record_id,
        timestamp,
        content,
        content_hash,
        previous_record_hash,
        record_hash,
        signature: hex::encode(signature.to_bytes()),
        signer_public_key: signer.public_key_hex(),
    })
}

/// Recompute every hash and check the signature of one record.
pub fn verify_record(record: &EvidenceRecord) -> Result<()> {
    let expected = content_hash(&record.content)?;
    if expected != record.content_hash {
        return Err(Error::Integrity(format!("{}: content hash mismatch", record.record_id)));
    }
    let expected = chain_hash(
        &record.content_hash,
        record.previous_record_hash.as_deref(),
        &record.record_id,
        &record.timestamp,
    );
    if expected != record.record_hash {
        return Err(Error::Integrity(format!("{}: record hash mismatch", record.record_id)));
    }
    let pk_bytes: [u8; 32] = hex::decode(&record.signer_public_key)
        .ok()
        .and_then(|v| v.try_into().ok())
        .ok_or_else(|| Error::Integrity("bad public key".into()))?;
    let pk = VerifyingKey::from_bytes(&pk_bytes).map_err(|e| Error::Integrity(e.to_string()))?;
    let sig_bytes: [u8; 64] = hex::decode(&record.signature)
        .ok()
        .and_then(|v| v.try_into().ok())
        .ok_or_else(|| Error::Integrity("bad signature encoding".into()))?;
    let sig = Signature::from_bytes(&sig_bytes);
    pk.verify(record.record_hash.as_bytes(), &sig)
        .map_err(|_| Error::Integrity(format!("{}: signature does not verify", record.record_id)))
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
    fn content_hash_is_independent_of_time_and_id() {
        let signer = RecordSigner::generate();
        let a = seal(content(1), None, "a".into(), "2026-01-01T00:00:00Z".into(), &signer).unwrap();
        let b = seal(content(1), None, "b".into(), "2027-01-01T00:00:00Z".into(), &signer).unwrap();
        assert_eq!(a.content_hash, b.content_hash);
        assert_ne!(a.record_hash, b.record_hash);
    }
}
