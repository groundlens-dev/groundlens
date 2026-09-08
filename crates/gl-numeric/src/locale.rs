//! How a corpus writes numbers. From an argument, never from the environment.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LocaleProfile {
    pub name: &'static str,
    pub decimal_sep: Option<char>,
    pub group_sep: Option<char>,
    /// Long scale: `billón` = 10^12 (es, de, fr, it, pt, nl). Short scale:
    /// `billion` = 10^9 (en). Unknown keeps the word form authoritative.
    pub long_scale: Option<bool>,
}

impl LocaleProfile {
    pub const fn known(&self) -> bool {
        self.decimal_sep.is_some()
    }
}

pub const LOCALES: &[LocaleProfile] = &[
    LocaleProfile { name: "und", decimal_sep: None, group_sep: None, long_scale: None },
    LocaleProfile { name: "en", decimal_sep: Some('.'), group_sep: Some(','), long_scale: Some(false) },
    LocaleProfile { name: "es", decimal_sep: Some(','), group_sep: Some('.'), long_scale: Some(true) },
    LocaleProfile { name: "ca", decimal_sep: Some(','), group_sep: Some('.'), long_scale: Some(true) },
    LocaleProfile { name: "de", decimal_sep: Some(','), group_sep: Some('.'), long_scale: Some(true) },
    LocaleProfile { name: "fr", decimal_sep: Some(','), group_sep: Some('\u{202F}'), long_scale: Some(true) },
    LocaleProfile { name: "it", decimal_sep: Some(','), group_sep: Some('.'), long_scale: Some(true) },
    LocaleProfile { name: "pt", decimal_sep: Some(','), group_sep: Some('.'), long_scale: Some(true) },
    LocaleProfile { name: "nl", decimal_sep: Some(','), group_sep: Some('.'), long_scale: Some(true) },
    LocaleProfile { name: "ch", decimal_sep: Some('.'), group_sep: Some('\''), long_scale: Some(true) },
];

pub fn locale(name: &str) -> Option<LocaleProfile> {
    let lower = name.to_ascii_lowercase();
    LOCALES.iter().copied().find(|l| l.name == lower)
}
