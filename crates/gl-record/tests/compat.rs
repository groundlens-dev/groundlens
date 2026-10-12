// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Records outlive releases.
//!
//! Every directory under `tests/fixtures/` holds records written by a released
//! version of GroundLens, signed with a fixed test key. They must keep
//! deserialising and verifying, signature and chain, with every later version.
//! A failure here means a change broke records that users already keep.
//! Never edit a fixture to make this test pass; add a reader instead.

use std::fs;
use std::path::{Path, PathBuf};

use gl_record::{
    verify_chain, verify_run_chain, EvidenceRecord, RunRecord, RECORD_SCHEMA, RUN_RECORD_SCHEMA,
};

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

fn read_lines(path: &Path) -> Vec<String> {
    fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()))
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(str::to_owned)
        .collect()
}

fn release_dirs() -> Vec<PathBuf> {
    let mut dirs: Vec<PathBuf> = fs::read_dir(fixtures())
        .expect("fixtures directory exists")
        .map(|e| e.unwrap().path())
        .filter(|p| p.is_dir())
        .collect();
    dirs.sort();
    assert!(!dirs.is_empty(), "at least one release fixture is committed");
    dirs
}

#[test]
fn answer_records_from_every_release_still_verify() {
    for dir in release_dirs() {
        let path = dir.join("answer-records.jsonl");
        if !path.exists() {
            continue;
        }
        let records: Vec<EvidenceRecord> = read_lines(&path)
            .iter()
            .map(|l| serde_json::from_str(l).unwrap_or_else(|e| panic!("{}: {e}", path.display())))
            .collect();
        assert!(records.len() >= 2, "{}: a chain needs at least two records", path.display());
        for r in &records {
            assert_eq!(r.content.schema, RECORD_SCHEMA, "{}: unknown schema", path.display());
        }
        verify_chain(&records).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    }
}

#[test]
fn run_records_from_every_release_still_verify() {
    for dir in release_dirs() {
        let path = dir.join("run-records.jsonl");
        if !path.exists() {
            continue;
        }
        let records: Vec<RunRecord> = read_lines(&path)
            .iter()
            .map(|l| serde_json::from_str(l).unwrap_or_else(|e| panic!("{}: {e}", path.display())))
            .collect();
        for r in &records {
            assert_eq!(r.content.schema, RUN_RECORD_SCHEMA, "{}: unknown schema", path.display());
        }
        verify_run_chain(&records).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    }
}

#[test]
fn a_tampered_fixture_is_rejected() {
    let dir = release_dirs().pop().unwrap();
    let path = dir.join("answer-records.jsonl");
    let mut records: Vec<EvidenceRecord> =
        read_lines(&path).iter().map(|l| serde_json::from_str(l).unwrap()).collect();
    records[0].content.locale = "xx".into();
    assert!(verify_chain(&records).is_err(), "changing a sealed field must break verification");
}
