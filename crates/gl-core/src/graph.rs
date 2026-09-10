// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The evidence graph: every piece of evidence, indexed by claim, in a
//! canonical order. The policy engine reads this. Nothing else writes it.

use serde::{Deserialize, Serialize};

use crate::{Evidence, EvidenceResult, VerifierInfo};

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct EvidenceGraph {
    pub verifiers: Vec<VerifierInfo>,
    pub evidence: Vec<Evidence>,
    /// Verifiers that were requested but produced an engine-level error.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub failures: Vec<(String, String)>,
}

impl EvidenceGraph {
    pub fn push_verifier(&mut self, info: VerifierInfo, evidence: Vec<Evidence>) {
        self.verifiers.push(info);
        self.evidence.extend(evidence);
        self.normalise();
    }

    pub fn push_failure(&mut self, verifier_id: &str, message: &str) {
        self.failures.push((verifier_id.to_string(), message.to_string()));
        self.failures.sort();
    }

    /// Canonical order. Called after every mutation so the graph serialises
    /// identically regardless of the order verifiers ran in.
    pub fn normalise(&mut self) {
        self.verifiers.sort_by(|a, b| a.id.cmp(&b.id));
        self.evidence.sort_by_key(|e| e.sort_key());
    }

    pub fn for_claim<'a>(&'a self, claim_id: &'a str) -> impl Iterator<Item = &'a Evidence> + 'a {
        self.evidence.iter().filter(move |e| e.claim_id == claim_id)
    }

    pub fn by_verifier<'a>(&'a self, verifier_id: &'a str) -> impl Iterator<Item = &'a Evidence> + 'a {
        self.evidence.iter().filter(move |e| e.verifier_id == verifier_id)
    }

    /// Claims for which two verifiers disagree on support versus
    /// contradiction. Policies usually route these to review.
    pub fn conflicts(&self) -> Vec<String> {
        let mut claims: Vec<&str> = self.evidence.iter().map(|e| e.claim_id.as_str()).collect();
        claims.sort();
        claims.dedup();
        claims
            .into_iter()
            .filter(|c| {
                let mut supported = false;
                let mut contradicted = false;
                for e in self.for_claim(c) {
                    match e.result {
                        EvidenceResult::Supported => supported = true,
                        EvidenceResult::Contradicted => contradicted = true,
                        _ => {}
                    }
                }
                supported && contradicted
            })
            .map(str::to_string)
            .collect()
    }
}
