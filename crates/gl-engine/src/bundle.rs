//! Loading a bundle once per process. A 470 MB encoder is not something to
//! read on every call.

use gl_bundle::Bundle;
use gl_core::Result;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};

pub const MISSING_BASE: &str = "the policy requires groundlens.lexical, which needs the base bundle (multilingual-e5-small). Install it once with `groundlens bundle pull base`, or point GROUNDLENS_BUNDLE_DIR at a bundle directory";

/// A verified bundle with its encoder loaded.
pub struct Loaded {
    pub root: PathBuf,
    pub name: String,
    pub version: String,
    pub manifest_hash: String,
    pub model_hash: String,
    #[cfg(feature = "lexical")]
    pub encoder: Arc<dyn gl_onnx::Encoder>,
}

fn cache() -> &'static Mutex<HashMap<PathBuf, Arc<Loaded>>> {
    static CACHE: OnceLock<Mutex<HashMap<PathBuf, Arc<Loaded>>>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

/// Resolve `spec`: a directory, a known bundle name, or `None` for the
/// installed `base` bundle. `Ok(None)` means no bundle is available.
pub fn resolve(spec: Option<&str>) -> Result<Option<PathBuf>> {
    let dir = match spec {
        Some(s) if Path::new(s).join("manifest.json").is_file() => PathBuf::from(s),
        Some(s) if Path::new(s).is_dir() => {
            return Err(gl_core::Error::Integrity(format!("{s}: no manifest.json in that directory")))
        }
        Some(name) => gl_bundle::locate(name),
        None => gl_bundle::locate("base"),
    };
    if dir.join("manifest.json").is_file() {
        Ok(Some(dir))
    } else if spec.is_some() {
        Err(gl_core::Error::Integrity(format!(
            "bundle {:?} is not installed ({})",
            spec.unwrap(),
            dir.display()
        )))
    } else {
        Ok(None)
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

#[cfg(feature = "lexical")]
fn build(bundle: Bundle) -> Result<Loaded> {
    let (encoder, model_hash) = gl_onnx::encoder_from_bundle(&bundle, "default")?;
    Ok(Loaded {
        root: bundle.root.clone(),
        name: bundle.manifest.name.clone(),
        version: bundle.manifest.version.clone(),
        manifest_hash: bundle.manifest_hash.clone(),
        model_hash,
        encoder: Arc::new(encoder),
    })
}

#[cfg(not(feature = "lexical"))]
fn build(bundle: Bundle) -> Result<Loaded> {
    Ok(Loaded {
        root: bundle.root.clone(),
        name: bundle.manifest.name.clone(),
        version: bundle.manifest.version.clone(),
        manifest_hash: bundle.manifest_hash.clone(),
        model_hash: String::new(),
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
