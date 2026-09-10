// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Numbers, decided by arithmetic. With units this time.
//!
//! groundlens 3.x compared bare values: `10,000` against `10000`. That is
//! exact and it is also blind to the most common reformatting in financial
//! and technical text: `$37.35 billion` against a table cell that says
//! `37,350` under a header "in millions", `1.2 km` against `1200 m`,
//! `4.75%` against `4,75 %`. This crate parses a numeral into a
//! [`Quantity`] (value, scale, dimension, unit) and compares quantities in a
//! canonical base unit with exact rational arithmetic. No floats anywhere.
//!
//! The equality relation stays strict by default. Rounding and the
//! percent-as-fraction reading are *named* relaxations a policy switches on,
//! and every relaxed match carries a note saying which one applied.

pub mod locale;
pub mod numeral;
pub mod quantity;
pub mod units;

pub use locale::{locale, LocaleProfile};
pub use numeral::{find_numerals, Numeral};
pub use quantity::{compare, find_bare_numerals, find_quantities, Match, MatchOptions, Quantity};
pub use units::{Dimension, Unit};
