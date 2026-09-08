use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("invalid input: {0}")]
    InvalidInput(String),

    #[error("verifier {verifier} failed: {message}")]
    Verifier { verifier: String, message: String },

    #[error("verifier {0} is not available in this bundle")]
    VerifierUnavailable(String),

    #[error("serialisation error: {0}")]
    Serialisation(String),

    #[error("integrity error: {0}")]
    Integrity(String),
}

pub type Result<T> = std::result::Result<T, Error>;

impl From<serde_json::Error> for Error {
    fn from(value: serde_json::Error) -> Self {
        Error::Serialisation(value.to_string())
    }
}
