// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Units and dimensions with exact conversion factors.
//!
//! A conversion is `base = (value * num + offset_num) / den`, all in
//! `Decimal`, so `°F` to kelvin is `(5, 2298.35, 9)` and stays exact. Two
//! quantities are compared in their dimension's base unit by
//! cross-multiplication, so no division ever happens.

use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Dimension {
    Dimensionless,
    Percent,
    /// ISO 4217 code. `$` is read as USD unless the locale says otherwise.
    Currency(String),
    Length,
    Mass,
    Time,
    Temperature,
    Energy,
    Power,
    Volume,
    Area,
    Data,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Unit {
    /// Canonical symbol: `m`, `kWh`, `EUR`, `%`, `°C`.
    pub symbol: &'static str,
    pub dimension: Dimension,
    /// Base-unit value = (value * num + offset_num) / den.
    pub num: Decimal,
    pub den: Decimal,
    pub offset_num: Decimal,
}

impl Unit {
    fn linear(symbol: &'static str, dimension: Dimension, num: Decimal, den: Decimal) -> Unit {
        Unit { symbol, dimension, num, den, offset_num: Decimal::ZERO }
    }

    pub fn dimensionless() -> Unit {
        Unit::linear("", Dimension::Dimensionless, Decimal::ONE, Decimal::ONE)
    }

    pub fn percent() -> Unit {
        Unit::linear("%", Dimension::Percent, Decimal::ONE, Decimal::ONE)
    }

    pub fn currency(code: &str) -> Unit {
        let symbol: &'static str = match code {
            "USD" => "USD",
            "EUR" => "EUR",
            "GBP" => "GBP",
            "JPY" => "JPY",
            "INR" => "INR",
            "CHF" => "CHF",
            _ => "XXX",
        };
        Unit::linear(symbol, Dimension::Currency(code.to_string()), Decimal::ONE, Decimal::ONE)
    }
}

/// One scale word: `million`, `mil millones`, `bn`. Applied before the unit.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Scale {
    pub word: &'static str,
    pub exponent: u32,
    /// `Some(true)` only valid in long-scale locales, `Some(false)` only in
    /// short-scale ones, `None` unambiguous.
    pub long_scale_only: Option<bool>,
}

/// Scale words, longest first so `mil millones` wins over `mil`.
pub const SCALES: &[Scale] = &[
    Scale { word: "mil millones", exponent: 9, long_scale_only: None },
    Scale { word: "mil millons", exponent: 9, long_scale_only: None },
    Scale { word: "milliards", exponent: 9, long_scale_only: None },
    Scale { word: "milliard", exponent: 9, long_scale_only: None },
    Scale { word: "milliarden", exponent: 9, long_scale_only: None },
    Scale { word: "milliarde", exponent: 9, long_scale_only: None },
    Scale { word: "thousand", exponent: 3, long_scale_only: None },
    Scale { word: "trillion", exponent: 12, long_scale_only: Some(false) },
    Scale { word: "trillón", exponent: 18, long_scale_only: Some(true) },
    Scale { word: "trillones", exponent: 18, long_scale_only: Some(true) },
    Scale { word: "billion", exponent: 9, long_scale_only: Some(false) },
    Scale { word: "billón", exponent: 12, long_scale_only: Some(true) },
    Scale { word: "billones", exponent: 12, long_scale_only: Some(true) },
    Scale { word: "millones", exponent: 6, long_scale_only: None },
    Scale { word: "millón", exponent: 6, long_scale_only: None },
    Scale { word: "millions", exponent: 6, long_scale_only: None },
    Scale { word: "million", exponent: 6, long_scale_only: None },
    Scale { word: "millionen", exponent: 6, long_scale_only: None },
    Scale { word: "milions", exponent: 6, long_scale_only: None },
    Scale { word: "milió", exponent: 6, long_scale_only: None },
    Scale { word: "mil", exponent: 3, long_scale_only: None },
    Scale { word: "bn", exponent: 9, long_scale_only: None },
    Scale { word: "mn", exponent: 6, long_scale_only: None },
    Scale { word: "MM", exponent: 6, long_scale_only: None },
    Scale { word: "M", exponent: 6, long_scale_only: None },
    Scale { word: "k", exponent: 3, long_scale_only: None },
    Scale { word: "B", exponent: 9, long_scale_only: None },
];

/// Look a unit symbol or name up. Case sensitive where SI is (`m` vs `M`),
/// insensitive for currency names and codes.
pub fn unit_for(token: &str) -> Option<Unit> {
    use Dimension as D;
    let one = Decimal::ONE;
    let d = |s: &str| Decimal::from_str_exact(s).expect("factor");
    let lower = token.to_lowercase();
    let cur = |code: &str| Some(Unit::currency(code));

    // Currency: symbols, codes, names.
    match lower.as_str() {
        "$" | "usd" | "dollar" | "dollars" | "dólar" | "dólares" | "us$" => return cur("USD"),
        "€" | "eur" | "euro" | "euros" => return cur("EUR"),
        "£" | "gbp" | "pound" | "pounds" | "libra" | "libras" => return cur("GBP"),
        "¥" | "jpy" | "yen" => return cur("JPY"),
        "₹" | "inr" | "rupee" | "rupees" => return cur("INR"),
        "chf" | "franc" | "francs" | "franco" | "francos" => return cur("CHF"),
        "%" | "٪" | "percent" | "por ciento" | "pct" => return Some(Unit::percent()),
        _ => {}
    }

    let u = match token {
        // Length, base metre.
        "m" | "metre" | "metres" | "meter" | "meters" | "metro" | "metros" => {
            Unit::linear("m", D::Length, one, one)
        }
        "km" | "kilometre" | "kilometres" | "kilometer" | "kilometers" | "kilómetro" | "kilómetros" => {
            Unit::linear("m", D::Length, d("1000"), one)
        }
        "cm" => Unit::linear("m", D::Length, one, d("100")),
        "mm" => Unit::linear("m", D::Length, one, d("1000")),
        "mi" | "mile" | "miles" | "milla" | "millas" => Unit::linear("m", D::Length, d("1609.344"), one),
        "ft" | "feet" | "foot" => Unit::linear("m", D::Length, d("0.3048"), one),
        "inch" | "inches" => Unit::linear("m", D::Length, d("0.0254"), one),
        // Mass, base kilogram.
        "kg" | "kilogram" | "kilograms" | "kilo" | "kilos" | "kilogramo" | "kilogramos" => {
            Unit::linear("kg", D::Mass, one, one)
        }
        "g" | "gram" | "grams" | "gramo" | "gramos" => Unit::linear("kg", D::Mass, one, d("1000")),
        "mg" => Unit::linear("kg", D::Mass, one, d("1000000")),
        "t" | "tonne" | "tonnes" | "tonelada" | "toneladas" => Unit::linear("kg", D::Mass, d("1000"), one),
        "lb" | "lbs" | "pound_mass" => Unit::linear("kg", D::Mass, d("0.45359237"), one),
        // Time, base second.
        "s" | "sec" | "second" | "seconds" | "segundo" | "segundos" => Unit::linear("s", D::Time, one, one),
        "ms" => Unit::linear("s", D::Time, one, d("1000")),
        "min" | "minute" | "minutes" | "minuto" | "minutos" => Unit::linear("s", D::Time, d("60"), one),
        "h" | "hr" | "hour" | "hours" | "hora" | "horas" => Unit::linear("s", D::Time, d("3600"), one),
        "day" | "days" | "día" | "días" => Unit::linear("s", D::Time, d("86400"), one),
        // Temperature, base kelvin.
        "K" | "kelvin" => Unit::linear("K", D::Temperature, one, one),
        "°C" | "ºC" | "celsius" => {
            Unit { symbol: "K", dimension: D::Temperature, num: one, den: one, offset_num: d("273.15") }
        }
        "°F" | "ºF" | "fahrenheit" => Unit {
            symbol: "K",
            dimension: D::Temperature,
            num: d("5"),
            den: d("9"),
            offset_num: d("2298.35"),
        },
        // Energy, base watt-hour (what utilities and batteries use).
        "Wh" => Unit::linear("Wh", D::Energy, one, one),
        "kWh" => Unit::linear("Wh", D::Energy, d("1000"), one),
        "MWh" => Unit::linear("Wh", D::Energy, d("1000000"), one),
        "GWh" => Unit::linear("Wh", D::Energy, d("1000000000"), one),
        "TWh" => Unit::linear("Wh", D::Energy, d("1000000000000"), one),
        "J" => Unit::linear("Wh", D::Energy, one, d("3600")),
        "kJ" => Unit::linear("Wh", D::Energy, d("1000"), d("3600")),
        "MJ" => Unit::linear("Wh", D::Energy, d("1000000"), d("3600")),
        // Power, base watt.
        "W" => Unit::linear("W", D::Power, one, one),
        "kW" => Unit::linear("W", D::Power, d("1000"), one),
        "MW" => Unit::linear("W", D::Power, d("1000000"), one),
        "GW" => Unit::linear("W", D::Power, d("1000000000"), one),
        // Volume, base litre.
        "l" | "L" | "litre" | "litres" | "liter" | "liters" | "litro" | "litros" => {
            Unit::linear("L", D::Volume, one, one)
        }
        "ml" | "mL" => Unit::linear("L", D::Volume, one, d("1000")),
        "m3" | "m³" => Unit::linear("L", D::Volume, d("1000"), one),
        "hl" => Unit::linear("L", D::Volume, d("100"), one),
        // Area, base square metre.
        "m2" | "m²" => Unit::linear("m2", D::Area, one, one),
        "ha" | "hectare" | "hectares" | "hectárea" | "hectáreas" => {
            Unit::linear("m2", D::Area, d("10000"), one)
        }
        "km2" | "km²" => Unit::linear("m2", D::Area, d("1000000"), one),
        // Data, base byte, decimal prefixes (IEC prefixes are separate).
        "bytes" | "byte" => Unit::linear("B", D::Data, one, one),
        "KB" | "kB" => Unit::linear("B", D::Data, d("1000"), one),
        "MB" => Unit::linear("B", D::Data, d("1000000"), one),
        "GB" => Unit::linear("B", D::Data, d("1000000000"), one),
        "TB" => Unit::linear("B", D::Data, d("1000000000000"), one),
        "KiB" => Unit::linear("B", D::Data, d("1024"), one),
        "MiB" => Unit::linear("B", D::Data, d("1048576"), one),
        "GiB" => Unit::linear("B", D::Data, d("1073741824"), one),
        _ => return None,
    };
    Some(u)
}

pub(crate) fn pow10(exponent: u32) -> Decimal {
    let mut v = Decimal::ONE;
    for _ in 0..exponent {
        v *= Decimal::from(10);
    }
    v
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn si_prefixes_are_case_sensitive() {
        assert_eq!(unit_for("m").unwrap().dimension, Dimension::Length);
        assert!(unit_for("M").is_none()); // M is a scale, not a unit
        assert_eq!(unit_for("MWh").unwrap().num, Decimal::from(1_000_000));
    }

    #[test]
    fn currency_names_are_case_insensitive() {
        assert_eq!(unit_for("Euros").unwrap().dimension, Dimension::Currency("EUR".into()));
        assert_eq!(unit_for("$").unwrap().dimension, Dimension::Currency("USD".into()));
    }
}
