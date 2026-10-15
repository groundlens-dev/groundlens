// SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
//
// SPDX-License-Identifier: Apache-2.0

//! Exact rational arithmetic and rounding rules.
//!
//! A derived figure (a difference, a ratio, a percentage change) is computed
//! as an exact fraction of two integers, never as a float and never by
//! dividing decimals. Whether it matches the figure the answer wrote is then a
//! question of rounding: the answer wrote `-7.92 %`, the exact value is
//! `-7.9166…`, and the rounding rule says whether one is the other at the
//! precision the answer chose. Every operation is checked: an overflow means
//! "cannot be shown", never a panic and never a guess.

use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use std::cmp::Ordering;

/// An exact fraction `n / d` with `d > 0`, kept in lowest terms.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Ratio {
    n: i128,
    d: i128,
}

fn gcd(a: i128, b: i128) -> i128 {
    // Unsigned, so `i128::MIN` cannot overflow `abs`. The result divides a
    // positive `i128` denominator, so it fits back into `i128`.
    let (mut a, mut b) = (a.unsigned_abs(), b.unsigned_abs());
    while b != 0 {
        let t = a % b;
        a = b;
        b = t;
    }
    i128::try_from(a.max(1)).unwrap_or(1)
}

impl Ratio {
    pub const ZERO: Ratio = Ratio { n: 0, d: 1 };

    fn new(n: i128, d: i128) -> Option<Ratio> {
        if d == 0 {
            return None;
        }
        let (n, d) = if d < 0 { (n.checked_neg()?, d.checked_neg()?) } else { (n, d) };
        let g = gcd(n, d);
        Some(Ratio { n: n / g, d: d / g })
    }

    pub fn from_int(n: i128) -> Ratio {
        Ratio { n, d: 1 }
    }

    /// The exact value of a decimal: `24.05` is `481 / 20`.
    pub fn from_decimal(v: Decimal) -> Option<Ratio> {
        let n = v.mantissa();
        let d = 10i128.checked_pow(v.scale())?;
        Ratio::new(n, d)
    }

    /// `10^e` for any integer `e`.
    pub fn pow10(e: i32) -> Option<Ratio> {
        let p = 10i128.checked_pow(e.unsigned_abs())?;
        if e >= 0 {
            Some(Ratio::from_int(p))
        } else {
            Ratio::new(1, p)
        }
    }

    pub fn checked_add(self, o: Ratio) -> Option<Ratio> {
        let n = self.n.checked_mul(o.d)?.checked_add(o.n.checked_mul(self.d)?)?;
        Ratio::new(n, self.d.checked_mul(o.d)?)
    }

    pub fn checked_sub(self, o: Ratio) -> Option<Ratio> {
        self.checked_add(o.checked_neg()?)
    }

    pub fn checked_mul(self, o: Ratio) -> Option<Ratio> {
        Ratio::new(self.n.checked_mul(o.n)?, self.d.checked_mul(o.d)?)
    }

    pub fn checked_div(self, o: Ratio) -> Option<Ratio> {
        Ratio::new(self.n.checked_mul(o.d)?, self.d.checked_mul(o.n)?)
    }

    pub fn checked_neg(self) -> Option<Ratio> {
        Some(Ratio { n: self.n.checked_neg()?, d: self.d })
    }

    pub fn checked_abs(self) -> Option<Ratio> {
        Some(Ratio { n: self.n.checked_abs()?, d: self.d })
    }

    pub fn is_zero(self) -> bool {
        self.n == 0
    }

    pub fn signum(self) -> i128 {
        self.n.signum()
    }

    /// `None` only if the cross products overflow.
    pub fn checked_cmp(self, o: Ratio) -> Option<Ordering> {
        Some(self.n.checked_mul(o.d)?.cmp(&o.n.checked_mul(self.d)?))
    }

    /// Exactly an integer, and that integer.
    fn as_integer(self) -> Option<i128> {
        (self.d == 1).then_some(self.n)
    }

    /// A short decimal rendering for receipts, at most six decimals. Display
    /// only; never used to decide anything.
    pub fn display(self) -> String {
        let scaled = self.n.checked_mul(1_000_000).map(|n| n / self.d);
        match scaled.and_then(|s| i64::try_from(s).ok()) {
            Some(s) => Decimal::new(s, 6).normalize().to_string(),
            None => format!("{}/{}", self.n, self.d),
        }
    }
}

/// How a computed value is allowed to differ from the figure an answer wrote,
/// at the precision the answer wrote it. A policy names one.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Rounding {
    /// Round to nearest, ties away from zero: `2.345` → `2.35`. What most
    /// people and most spreadsheets do.
    HalfUp,
    /// Round to nearest, ties to the even digit: `2.345` → `2.34`. Banking
    /// and IEEE practice.
    HalfEven,
    /// Rounded or truncated: anything strictly within one unit of the last
    /// digit written. `67.87…` matches `67.8` and `67.9`. The default since
    /// 6.0.3: language models cut digits as often as they round them, and a
    /// difference in the last digit written is not a wrong figure.
    #[default]
    WithinLastDigit,
}

/// Does the exact value `x` round to `written`, where `step` is one unit of
/// the last digit the answer wrote (`0.01` for `-7.92`)?
pub fn rounds_to(x: Ratio, written: Ratio, step: Ratio, rule: Rounding) -> bool {
    let check = || -> Option<bool> {
        let half = step.checked_div(Ratio::from_int(2))?;
        let (lo, hi) = (written.checked_sub(half)?, written.checked_add(half)?);
        let above_lo = x.checked_cmp(lo)?;
        let below_hi = x.checked_cmp(hi)?;
        let strictly_inside = above_lo == Ordering::Greater && below_hi == Ordering::Less;
        Some(match rule {
            Rounding::HalfUp => {
                // A tie goes away from zero, so the written value keeps the
                // tie on the side nearer zero.
                strictly_inside
                    || (written.signum() > 0 && above_lo == Ordering::Equal)
                    || (written.signum() < 0 && below_hi == Ordering::Equal)
            }
            Rounding::HalfEven => {
                let even = written.checked_div(step)?.as_integer().is_some_and(|k| k % 2 == 0);
                strictly_inside || (even && (above_lo == Ordering::Equal || below_hi == Ordering::Equal))
            }
            Rounding::WithinLastDigit => {
                let (lo, hi) = (written.checked_sub(step)?, written.checked_add(step)?);
                x.checked_cmp(lo)? == Ordering::Greater && x.checked_cmp(hi)? == Ordering::Less
            }
        })
    };
    check().unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::str::FromStr;

    fn r(s: &str) -> Ratio {
        Ratio::from_decimal(Decimal::from_str(s).unwrap()).unwrap()
    }

    #[test]
    fn fractions_are_exact() {
        let pct = r("22.1")
            .checked_sub(r("24.0"))
            .unwrap()
            .checked_div(r("24.0"))
            .unwrap()
            .checked_mul(r("100"))
            .unwrap();
        assert_eq!(pct, Ratio::new(-95, 12).unwrap(), "-7.91666…");
        assert!(rounds_to(pct, r("-7.92"), r("0.01"), Rounding::HalfUp));
        assert!(!rounds_to(pct, r("-7.91"), r("0.01"), Rounding::HalfUp));
        assert!(!rounds_to(pct, r("-7.9"), r("0.01"), Rounding::HalfUp));
    }

    #[test]
    fn ties_follow_the_rule() {
        let tie = r("2.345");
        assert!(rounds_to(tie, r("2.35"), r("0.01"), Rounding::HalfUp));
        assert!(!rounds_to(tie, r("2.34"), r("0.01"), Rounding::HalfUp));
        assert!(rounds_to(tie, r("2.34"), r("0.01"), Rounding::HalfEven));
        assert!(!rounds_to(tie, r("2.35"), r("0.01"), Rounding::HalfEven));
        let neg = r("-2.345");
        assert!(rounds_to(neg, r("-2.35"), r("0.01"), Rounding::HalfUp));
        assert!(!rounds_to(neg, r("-2.34"), r("0.01"), Rounding::HalfUp));
    }

    #[test]
    fn truncation_is_accepted_only_within_the_last_digit() {
        let x = r("957.4").checked_div(r("1410.5")).unwrap().checked_mul(r("100")).unwrap(); // 67.876…
        assert!(!rounds_to(x, r("67.8"), r("0.1"), Rounding::HalfUp));
        assert!(rounds_to(x, r("67.9"), r("0.1"), Rounding::HalfUp));
        assert!(rounds_to(x, r("67.8"), r("0.1"), Rounding::WithinLastDigit));
        assert!(!rounds_to(x, r("67.7"), r("0.1"), Rounding::WithinLastDigit));
    }

    #[test]
    fn overflow_is_not_a_match_and_not_a_panic() {
        let huge = Ratio::from_int(i128::MAX);
        assert!(huge.checked_mul(huge).is_none());
        assert!(!rounds_to(huge, Ratio::from_int(1), Ratio::from_int(1), Rounding::HalfUp));
        let min = Ratio::from_int(i128::MIN);
        assert!(min.checked_div(Ratio::from_int(3)).is_some_and(|r| r.signum() < 0));
        assert!(min.checked_abs().is_none());
    }
}
