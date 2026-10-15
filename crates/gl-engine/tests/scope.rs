// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The scope check, end to end through the shipped default policy.
//!
//! The case comes from a real retrieval failure: without a company filter,
//! the retriever returned a passage from another company's annual report and
//! the model took its figure. Every figure exists in some source, so a check
//! that only asks "is this number in the sources?" passes it.

use gl_core::Source;
use gl_policy::Decision;
use groundlens::{verify, VerifyRequest};

fn source(id: &str, text: &str, entity: Option<&str>) -> Source {
    let mut provenance = indexmap::IndexMap::new();
    if let Some(e) = entity {
        provenance.insert("entity".to_string(), e.to_string());
    }
    Source { id: id.into(), text: text.into(), locator: None, provenance }
}

fn request(answer: &str, sources: Vec<Source>, entity: Option<&str>) -> VerifyRequest {
    let mut req = VerifyRequest::new(answer, sources);
    req.locale = "en".into();
    if let Some(e) = entity {
        req.scope.insert("entity".into(), e.into());
    }
    req
}

fn sources() -> Vec<Source> {
    vec![
        source(
            "IP/2007/page_75",
            "The company recorded an income tax provision of $1.9 billion.",
            Some("IP"),
        ),
        source("AAPL/2006/page_100", "Provision for income taxes was $829 million.", Some("AAPL")),
    ]
}

#[test]
fn a_figure_from_another_company_fails_when_the_scope_is_stated() {
    let record = verify(&request("The 2006 tax expense was $1.9 billion.", sources(), Some("AAPL"))).unwrap();
    assert_eq!(record.content.outcome.decision, Decision::Fail);
    let reasons: Vec<&String> = record.content.outcome.claims.iter().flat_map(|c| c.reasons.iter()).collect();
    assert!(reasons
        .iter()
        .any(|r| r.contains("groundlens.scope") && r.contains("outside the request scope")));
    gl_record::verify_record(&record).unwrap();
}

#[test]
fn the_same_answer_passes_without_a_scope_which_is_the_gap_the_check_closes() {
    let record = verify(&request("The 2006 tax expense was $1.9 billion.", sources(), None)).unwrap();
    assert_eq!(record.content.outcome.decision, Decision::Pass);
    assert!(!record.content.graph.verifiers.iter().any(|v| v.id == "groundlens.scope"));
}

#[test]
fn a_figure_from_inside_the_scope_passes() {
    let record = verify(&request("The 2006 tax expense was $829 million.", sources(), Some("AAPL"))).unwrap();
    assert_eq!(record.content.outcome.decision, Decision::Pass);
}

#[test]
fn a_figure_from_a_passage_without_provenance_goes_to_review() {
    let record = verify(&request(
        "Revenue was $10 million.",
        vec![source("s", "Revenue was $10 million.", None)],
        Some("AAPL"),
    ))
    .unwrap();
    assert_eq!(record.content.outcome.decision, Decision::Review);
}

#[test]
fn scope_and_provenance_are_part_of_the_input_hash() {
    let with = verify(&request("Revenue was $829 million.", sources(), Some("AAPL"))).unwrap();
    let other = verify(&request("Revenue was $829 million.", sources(), Some("IP"))).unwrap();
    assert_ne!(with.content.input_hash, other.content.input_hash);
}
