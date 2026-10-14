// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! The intent check, end to end through the shipped default policy. The case
//! is a real answer: asked what portion of the obligations is related to
//! equity, the model gave the dollar amount, which is in the source, so every
//! other check passes it.

use gl_core::Source;
use gl_engine::{verify, VerifyRequest};
use gl_policy::Decision;

fn request(question: Option<&str>, answer: &str) -> VerifyRequest {
    let mut req = VerifyRequest::new(
        answer,
        vec![Source {
            id: "AAL/2013/page_172".into(),
            text: "single-dip equity obligations | 1,246 | total obligations | 5,424".into(),
            locator: None,
            provenance: Default::default(),
        }],
    );
    req.locale = "en".into();
    req.question = question.map(str::to_string);
    req
}

#[test]
fn an_amount_given_for_a_portion_asked_goes_to_review() {
    let q = "What portion of the total bankruptcy settlement obligations are related to single-dip equity obligations?";
    let record =
        verify(&request(Some(q), "The portion related to single-dip equity obligations is $1,246 million."))
            .unwrap();
    assert_eq!(record.content.outcome.decision, Decision::Review);
    let reasons: Vec<&String> = record.content.outcome.claims.iter().flat_map(|c| c.reasons.iter()).collect();
    assert!(
        reasons.iter().any(|r| r.contains("groundlens.intent") && r.contains("asks for a percentage")),
        "{reasons:?}"
    );
    gl_record::verify_record(&record).unwrap();
}

#[test]
fn the_kind_asked_passes_and_without_a_question_the_check_does_not_run() {
    let q = "What portion of the total obligations is related to single-dip equity obligations?";
    let ok = verify(&request(Some(q), "It is 1,246 of 5,424, or 22.97%.")).unwrap();
    assert_eq!(ok.content.outcome.decision, Decision::Pass);
    let none = verify(&request(None, "The portion is $1,246 million.")).unwrap();
    assert!(!none.content.graph.verifiers.iter().any(|v| v.id == "groundlens.intent"));
}
