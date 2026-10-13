// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Loading a bundle once per process. A 470 MB encoder is not something to
//! read on every call.

use gl_bundle::Bundle;
use gl_core::Result;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};

pub const MISSING_BASE: &str = "the policy requires groundlens.lexical, which needs a model bundle, and the request names none. Model bundles are no longer used unless you ask for one: pass `--bundle base` (Python: `bundle=\"base\"`) after installing it once with `groundlens bundle pull base`. The model channels are deprecated and leave the default build in the next release";

/// Printed by the command-line tools when a request names a bundle.
pub const DEPRECATED: &str = "warning: the model channels (lexical, entailment, similarity) are deprecated. They did not add value on the answers we measured, and they leave the default build in the next release. The default path needs no model";

pub const MISSING_NLI: &str = "the policy requires groundlens.nli, which needs a bundle carrying an entailment model. Name one with `--bundle` (Python: `bundle=...`) whose manifest declares an `entailment` model. The model channels are deprecated and leave the default build in the next release";

/// A verified bundle with its models loaded.
pub struct Loaded {
    pub root: PathBuf,
    pub name: String,
    pub version: String,
    pub manifest_hash: String,
    pub model_hash: String,
    #[cfg(any(feature = "lexical", feature = "semantic"))]
    pub encoder: Arc<dyn gl_onnx::Encoder>,
    /// The entailment model and its hash, when the bundle declares one.
    #[cfg(feature = "nli")]
    pub entailment: Option<(Arc<dyn gl_onnx::EntailmentModel>, String)>,
}

fn cache() -> &'static Mutex<HashMap<PathBuf, Arc<Loaded>>> {
    static CACHE: OnceLock<Mutex<HashMap<PathBuf, Arc<Loaded>>>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

/// Resolve `spec`: a directory or a known bundle name. `None` resolves to no
/// bundle, even when one is installed: the model channels run only when the
/// request asks for them. A named bundle that is not installed is an error.
pub fn resolve(spec: Option<&str>) -> Result<Option<PathBuf>> {
    let Some(spec) = spec else { return Ok(None) };
    let dir = match spec {
        s if Path::new(s).join("manifest.json").is_file() => PathBuf::from(s),
        s if Path::new(s).is_dir() => {
            return Err(gl_core::Error::Integrity(format!("{s}: no manifest.json in that directory")))
        }
        name => gl_bundle::locate(name),
    };
    if dir.join("manifest.json").is_file() {
        Ok(Some(dir))
    } else {
        Err(gl_core::Error::Integrity(format!("bundle {spec:?} is not installed ({})", dir.display())))
    }
}

/// Load (or fetch from the cache) the bundle `spec` names.
pub fn load(spec: Option<&str>) -> Result<Option<Arc<Loaded>>> {
    let Some(dir) = resolve(spec)? else { return Ok(None) };
    let dir = dir.canonicalize().unwrap_or(dir);
    if let Some(l) = cache().lock().expect("bundle cache").get(&dir) {
        return Ok(Some(l.clone()));
    }
    let bundle = Bundle::open(&dir)?;
    let loaded = Arc::new(build(bundle)?);
    cache().lock().expect("bundle cache").insert(dir, loaded.clone());
    Ok(Some(loaded))
}

fn build(bundle: Bundle) -> Result<Loaded> {
    #[cfg(any(feature = "lexical", feature = "semantic"))]
    let (encoder, model_hash) = {
        let (enc, hash) = gl_onnx::encoder_from_bundle(&bundle, "default")?;
        (Arc::new(enc) as Arc<dyn gl_onnx::Encoder>, hash)
    };
    #[cfg(not(any(feature = "lexical", feature = "semantic")))]
    let model_hash = String::new();

    #[cfg(feature = "nli")]
    let entailment = if bundle.manifest.entailment.contains_key("default") {
        let (model, hash) = gl_onnx::entailment_from_bundle(&bundle, "default")?;
        Some((Arc::new(model) as Arc<dyn gl_onnx::EntailmentModel>, hash))
    } else {
        None
    };

    Ok(Loaded {
        root: bundle.root.clone(),
        name: bundle.manifest.name.clone(),
        version: bundle.manifest.version.clone(),
        manifest_hash: bundle.manifest_hash.clone(),
        model_hash,
        #[cfg(any(feature = "lexical", feature = "semantic"))]
        encoder,
        #[cfg(feature = "nli")]
        entailment,
    })
}

/// What `groundlens bundle status` prints.
#[derive(Debug, serde::Serialize)]
pub struct Status {
    pub name: String,
    pub installed: bool,
    pub path: String,
    pub version: Option<String>,
    pub manifest_hash: Option<String>,
    pub url: String,
    pub archive_sha256: String,
    pub description: String,
}

pub fn status(name: &str) -> Status {
    let known = gl_bundle::known(name);
    let path = gl_bundle::locate(name);
    let opened = if path.join("manifest.json").is_file() { Bundle::open(&path).ok() } else { None };
    Status {
        name: name.to_string(),
        installed: opened.is_some(),
        path: path.display().to_string(),
        version: opened.as_ref().map(|b| b.manifest.version.clone()),
        manifest_hash: opened.as_ref().map(|b| b.manifest_hash.clone()),
        url: known.map(|k| k.url.to_string()).unwrap_or_default(),
        archive_sha256: known.map(|k| k.archive_sha256.to_string()).unwrap_or_default(),
        description: known.map(|k| k.description.to_string()).unwrap_or_default(),
    }
}
