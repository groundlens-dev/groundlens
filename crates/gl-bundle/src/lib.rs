//! The verification bundle: engine + ONNX models + tokenizers + rules +
//! policies + checksums, in one directory that needs no network.
//!
//! ```text
//! bundle/
//! ├── manifest.json          this file, hashed into every record as bundle_hash
//! ├── models/
//! │   ├── nli-deberta-v3-small.onnx
//! │   └── all-mpnet-base-v2.onnx
//! ├── tokenizers/
//! │   └── all-mpnet-base-v2/tokenizer.json
//! ├── calibration/
//! │   └── sgi-finance-v1.json
//! ├── rules/
//! │   └── es_banking_v1.json
//! └── policies/
//!     └── eu_ai_act_high_risk_v1.yaml
//! ```
//!
//! Loading a bundle re-hashes every artefact and refuses to start on a
//! mismatch. There is no partial trust.

use gl_core::canonical::{content_hash, sha256_hex};
use gl_core::{Error, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Artefact {
    pub path: String,
    pub sha256: String,
    #[serde(default)]
    pub bytes: u64,
    /// `onnx-model`, `tokenizer`, `calibration`, `ruleset`, `policy`.
    pub kind: String,
    /// Which verifier ids depend on this artefact.
    #[serde(default)]
    pub used_by: Vec<String>,
}

/// How to run one encoder. Plain data; `gl-onnx` turns it into a model.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncoderSpec {
    /// Bundle-relative path of the ONNX graph.
    pub model: String,
    /// Bundle-relative path of `tokenizer.json`.
    pub tokenizer: String,
    /// Content tokens per window, special tokens excluded.
    pub max_tokens: usize,
    /// Text prepended to every input (`"query: "` for the e5 family). Never
    /// part of a span.
    #[serde(default)]
    pub prefix: String,
    /// `mean` or `cls`, for the pooled sentence vector.
    #[serde(default = "mean")]
    pub pooling: String,
    #[serde(default)]
    pub dim: usize,
}

fn mean() -> String {
    "mean".into()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Manifest {
    pub schema: String,
    pub name: String,
    pub version: String,
    pub engine_version: String,
    /// `cpu-f32` today. Recorded so a GPU build can never masquerade as the
    /// reference execution profile.
    pub execution_profile: String,
    pub artefacts: BTreeMap<String, Artefact>,
    /// Bundles built for air-gapped sites set this to `true`; the engine
    /// then refuses any verifier whose `needs_network` is set.
    #[serde(default)]
    pub offline_only: bool,
    /// Encoders by role. The lexical verifier uses `default`.
    #[serde(default)]
    pub encoders: BTreeMap<String, EncoderSpec>,
    /// Where the artefacts came from (model repository, revision, files).
    /// Free-form, hashed with the rest of the manifest.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub provenance: Option<serde_json::Value>,
}

pub const MANIFEST_SCHEMA: &str = "groundlens.bundle-manifest/1";

impl Manifest {
    pub fn hash(&self) -> Result<String> {
        content_hash(self)
    }
}

pub struct Bundle {
    pub root: PathBuf,
    pub manifest: Manifest,
    pub manifest_hash: String,
}

impl Bundle {
    /// Open and verify every artefact. O(total bytes), once, at start-up.
    pub fn open(root: impl AsRef<Path>) -> Result<Bundle> {
        let root = root.as_ref().to_path_buf();
        let text = std::fs::read_to_string(root.join("manifest.json"))
            .map_err(|e| Error::Integrity(format!("manifest.json: {e}")))?;
        let manifest: Manifest = serde_json::from_str(&text)?;
        if manifest.schema != MANIFEST_SCHEMA {
            return Err(Error::Integrity(format!("unknown manifest schema {}", manifest.schema)));
        }
        for (id, a) in &manifest.artefacts {
            let bytes = std::fs::read(root.join(&a.path))
                .map_err(|e| Error::Integrity(format!("{id} ({}): {e}", a.path)))?;
            let actual = format!("sha256:{}", sha256_hex(&bytes));
            if actual != a.sha256 {
                return Err(Error::Integrity(format!("{id}: expected {} got {actual}", a.sha256)));
            }
        }
        let manifest_hash = manifest.hash()?;
        Ok(Bundle { root, manifest, manifest_hash })
    }

    pub fn artefact_path(&self, id: &str) -> Option<PathBuf> {
        self.manifest.artefacts.get(id).map(|a| self.root.join(&a.path))
    }
}

/// Build a manifest from a directory: hash everything under the known
/// sub-folders. Used by `glv bundle build`.
pub fn build_manifest(root: &Path, name: &str, version: &str, engine_version: &str) -> Result<Manifest> {
    let mut artefacts = BTreeMap::new();
    for (folder, kind) in [
        ("models", "onnx-model"),
        ("tokenizers", "tokenizer"),
        ("calibration", "calibration"),
        ("rules", "ruleset"),
        ("policies", "policy"),
    ] {
        let dir = root.join(folder);
        if !dir.is_dir() {
            continue;
        }
        let mut files: Vec<PathBuf> = walk(&dir)?;
        files.sort();
        for f in files {
            let rel = f.strip_prefix(root).expect("under root").to_string_lossy().replace('\\', "/");
            let bytes = std::fs::read(&f).map_err(|e| Error::Integrity(format!("{rel}: {e}")))?;
            artefacts.insert(
                rel.clone(),
                Artefact {
                    path: rel,
                    sha256: format!("sha256:{}", sha256_hex(&bytes)),
                    bytes: bytes.len() as u64,
                    kind: kind.to_string(),
                    used_by: vec![],
                },
            );
        }
    }
    Ok(Manifest {
        schema: MANIFEST_SCHEMA.into(),
        name: name.into(),
        version: version.into(),
        engine_version: engine_version.into(),
        execution_profile: "cpu-f32".into(),
        artefacts,
        offline_only: true,
        encoders: BTreeMap::new(),
        provenance: None,
    })
}

/// A bundle the engine knows how to fetch and verify. The archive hash is
/// pinned in the engine, so a download is trusted only if it matches what
/// this build was released with.
#[derive(Debug, Clone, Copy)]
pub struct KnownBundle {
    pub name: &'static str,
    pub version: &'static str,
    pub url: &'static str,
    /// `sha256:<hex>` of the `.tar.gz`, or `sha256:unpinned` before the
    /// first release of that bundle (pull then refuses).
    pub archive_sha256: &'static str,
    pub description: &'static str,
}

pub const KNOWN_BUNDLES: &[KnownBundle] = &[KnownBundle {
    name: "base",
    version: "1",
    url: "https://github.com/groundlens-dev/groundlens/releases/download/bundle-base-v1/groundlens-base-v1.tar.gz",
    archive_sha256: "sha256:unpinned",
    description: "multilingual-e5-small (f32) for the lexical channel; 100 languages",
}];

pub fn known(name: &str) -> Option<&'static KnownBundle> {
    KNOWN_BUNDLES.iter().find(|b| b.name == name)
}

/// Where bundles live on this machine, unless `GROUNDLENS_BUNDLE_DIR` says
/// otherwise: the per-user data directory of the OS.
pub fn bundles_home() -> PathBuf {
    if let Some(dir) = std::env::var_os("GROUNDLENS_BUNDLE_DIR") {
        return PathBuf::from(dir);
    }
    let home = std::env::var_os("HOME").or_else(|| std::env::var_os("USERPROFILE")).map(PathBuf::from);
    let base = if cfg!(target_os = "macos") {
        home.map(|h| h.join("Library/Application Support"))
    } else if cfg!(target_os = "windows") {
        std::env::var_os("LOCALAPPDATA").map(PathBuf::from).or(home)
    } else {
        std::env::var_os("XDG_DATA_HOME").map(PathBuf::from).or_else(|| home.map(|h| h.join(".local/share")))
    };
    base.unwrap_or_else(|| PathBuf::from(".")).join("groundlens").join("bundles")
}

/// The directory a named bundle would be installed in. `GROUNDLENS_BUNDLE_DIR`
/// pointing straight at a bundle (it contains `manifest.json`) is honoured
/// as that bundle, whatever its name.
pub fn locate(name: &str) -> PathBuf {
    let home = bundles_home();
    if home.join("manifest.json").is_file() {
        return home;
    }
    home.join(name)
}

/// Open the named bundle if it is installed; `Ok(None)` when it is not.
pub fn open_installed(name: &str) -> Result<Option<Bundle>> {
    let dir = locate(name);
    if !dir.join("manifest.json").is_file() {
        return Ok(None);
    }
    Bundle::open(dir).map(Some)
}

fn walk(dir: &Path) -> Result<Vec<PathBuf>> {
    let mut out = Vec::new();
    for entry in std::fs::read_dir(dir).map_err(|e| Error::Integrity(e.to_string()))? {
        let entry = entry.map_err(|e| Error::Integrity(e.to_string()))?;
        let path = entry.path();
        if path.is_dir() {
            out.extend(walk(&path)?);
        } else {
            out.push(path);
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_then_open_then_detect_tampering() {
        let dir = std::env::temp_dir().join(format!("gl-bundle-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(dir.join("policies")).unwrap();
        std::fs::write(dir.join("policies/p.yaml"), "id: p\nversion: 1\n").unwrap();
        let m = build_manifest(&dir, "test", "1", "0.1.0").unwrap();
        std::fs::write(dir.join("manifest.json"), serde_json::to_string_pretty(&m).unwrap()).unwrap();
        let b = Bundle::open(&dir).unwrap();
        assert!(b.manifest_hash.starts_with("sha256:"));
        std::fs::write(dir.join("policies/p.yaml"), "id: p\nversion: 2\n").unwrap();
        assert!(Bundle::open(&dir).is_err());
        let _ = std::fs::remove_dir_all(&dir);
    }
}
