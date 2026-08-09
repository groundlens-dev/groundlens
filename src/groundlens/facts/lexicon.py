"""Static, hand-audited word lists used by the fact extractor.

Everything in this module is data, not behaviour.  It is kept separate so that
adding a deontic cue or a month name is a one-line diff that cannot change
control flow, and so the lists can be reviewed by a domain expert who does not
read Python.

Two languages are covered in v1: English and Spanish.  Language is *not*
detected; both lexicons are always active.  That is deliberate — detection is
another guess, and the cue sets barely collide.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Deontic cues
# ---------------------------------------------------------------------------
#
# Each entry is (regex source, polarity value, form id, weak?).
#
# ORDER IS LOAD BEARING.  Candidates are resolved leftmost-longest, and ties at
# equal start and equal length fall back to this list order.  Negative forms are
# written as single units ("must not", "is not required to") rather than a
# positive cue plus a separate negation pass: a negation pass is exactly how an
# extractor ends up reporting MUST for a prohibition.
#
# "polarity" values match groundlens.types.Polarity string values.

_ADVERB_GAP: Final[str] = (
    r"(?:\s+(?:ever|at\s+any\s+time|in\s+any\s+way|knowingly|wilfully|willfully|"
    r"directly|indirectly|under\s+any\s+circumstances|on\s+any\s+account)){0,2}"
)
"""Adverbials tolerated between a modal and its negator ("must at any time not")."""

_NEVER: Final[str] = (
    r"(?:never|at\s+no\s+time|under\s+no\s+circumstances|in\s+no\s+event|on\s+no\s+account)"
)

DEONTIC_CUES: Final[tuple[tuple[str, str, str, bool], ...]] = (
    # -- prohibition -------------------------------------------------------
    (rf"\b(?:must|shall)\b{_ADVERB_GAP}\s+not\b", "must_not", "modal_not", False),
    (rf"\b(?:must|shall)\s+{_NEVER}\b", "must_not", "modal_never", False),
    (r"\b(?:mustn't|shan't|can't|won't)", "must_not", "modal_contraction", False),
    (r"\bmay\s+not\b", "must_not", "may_not", False),
    (r"\bmay\s+" + _NEVER + r"\b", "must_not", "may_never", False),
    (r"\b(?:is|are|was|were)\s+prohibited\s+(?:from|to)\b", "must_not", "prohibited", False),
    (r"\b(?:is|are)\s+forbidden\s+(?:from|to)\b", "must_not", "forbidden", False),
    (r"\b(?:is|are)\s+banned\s+from\b", "must_not", "banned", False),
    (r"\b(?:is|are)\s+barred\s+from\b", "must_not", "barred", False),
    (
        r"\b(?:is|are)\s+not\s+(?:permitted|allowed|authorised|authorized)\s+to\b",
        "must_not",
        "not_permitted",
        False,
    ),
    (r"\b(?:is|are)\s+required\s+not\s+to\b", "must_not", "required_not_to", False),
    (r"\b(?:must|shall)\s+(?:refrain|abstain)\s+from\b", "must_not", "refrain", False),
    (r"\bno\s+\w+(?:\s+\w+){0,2}\s+(?:may|shall)\b", "must_not", "no_subject_modal", False),
    (
        r"\bneither\s+[^.;\n]{1,80}?\bnor\s+[^.;\n]{1,60}?\s(?:may|shall|can)\b",
        "must_not",
        "neither_nor_modal",
        False,
    ),
    (
        r"\bni\s+[^.;\n]{1,80}?\bni\s+[^.;\n]{1,60}?\s(?:podr[\u00e1a]n?|puede[n]?|debe[n]?)\b",
        "must_not",
        "es_ni_ni",
        False,
    ),
    (r"\bcannot\b", "must_not", "cannot", True),
    (r"\bcan\s+not\b", "must_not", "can_not", True),
    (r"\bno\s+se\s+(?:permite|autoriza|podr[áa])\b", "must_not", "es_no_se_permite", False),
    (r"\b(?:queda|est[áa])\s+prohibid[oa]s?\b", "must_not", "es_prohibido", False),
    (r"\bse\s+proh[íi]be\b", "must_not", "es_se_prohibe", False),
    (r"\btiene\s+prohibido\b", "must_not", "es_tiene_prohibido", False),
    (r"\btienen\s+prohibido\b", "must_not", "es_tienen_prohibido", False),
    (r"\bno\s+(?:debe|deber[áa]n?|deben)\b", "must_not", "es_no_debe", False),
    (r"\bno\s+(?:puede|podr[áa]n?|pueden)\b", "must_not", "es_no_puede", True),
    (r"\bno\s+est[áa]\s+permitido\b", "must_not", "es_no_permitido", False),
    (r"\b(?:debe|deber[áa]n?)\s+abstenerse\s+de\b", "must_not", "es_abstenerse", False),
    (r"\bning[úu]n\w*\s+\w+(?:\s+\w+){0,2}\s+podr[áa]n?\b", "must_not", "es_ninguno", False),
    # -- exemption ---------------------------------------------------------
    (r"\bneed\s+not\b", "need_not", "need_not", False),
    (r"\bneedn't\b", "need_not", "neednt", False),
    (r"\b(?:does|do|did)\s+not\s+(?:need|have)\s+to\b", "need_not", "does_not_need", False),
    (
        r"\b(?:is|are)\s+not\s+(?:required|obliged|obligated)\s+to\b",
        "need_not",
        "not_required",
        False,
    ),
    (r"\b(?:is|are)\s+exempt(?:ed)?\s+from\b", "need_not", "exempt", False),
    (r"\b(?:is|are)\s+under\s+no\s+obligation\s+to\b", "need_not", "no_obligation", False),
    (r"\bha(?:s|ve)\s+no\s+obligation\s+to\b", "need_not", "has_no_obligation", False),
    (r"\bno\s+(?:est[áa]|est[áa]n)\s+obligad[oa]s?\s+a\b", "need_not", "es_no_obligado", False),
    (r"\bno\s+(?:tiene|tienen)\s+(?:la\s+)?obligaci[óo]n\s+de\b", "need_not", "es_sin_obl", False),
    (r"\b(?:est[áa]|est[áa]n)\s+exent[oa]s?\s+de\b", "need_not", "es_exento", False),
    (r"\bno\s+es\s+necesario\b", "need_not", "es_no_necesario", False),
    (r"\bno\s+(?:necesita|necesitan)\b", "need_not", "es_no_necesita", False),
    (r"\bno\s+hace\s+falta\b", "need_not", "es_no_hace_falta", False),
    # -- negative recommendation (no SHOULD_NOT in the frozen enum; see -----
    #    Polarity note in extract.py — encoded as SHOULD + direction=negative)
    (r"\bshould\b" + _ADVERB_GAP + r"\s+not\b", "should", "should_not", False),
    (r"\bshouldn't\b", "should", "shouldnt", False),
    (r"\bought\s+not\s+to\b", "should", "ought_not", False),
    (r"\b(?:is|are)\s+not\s+recommended\s+to\b", "should", "not_recommended_to", False),
    (r"\b(?:is|are)\s+discouraged\s+from\b", "should", "discouraged", False),
    (r"\bno\s+(?:deber[íi]a|deber[íi]an)\b", "should", "es_no_deberia", False),
    (r"\bno\s+se\s+recomienda\b", "should", "es_no_se_recomienda", False),
    # -- obligation --------------------------------------------------------
    (r"\b(?:is|are)\s+required\s+to\b", "must", "required_to", False),
    (r"\b(?:is|are)\s+obliged\s+to\b", "must", "obliged_to", False),
    (r"\b(?:is|are)\s+obligated\s+to\b", "must", "obligated_to", False),
    (r"\b(?:is|are)\s+under\s+an?\s+obligation\s+to\b", "must", "under_obligation", False),
    (r"\bha(?:s|ve)\s+to\b", "must", "has_to", False),
    (r"\bit\s+is\s+mandatory\s+(?:to|that|for)\b", "must", "mandatory", False),
    (r"\b(?:must|shall)\b", "must", "modal", False),
    (r"\best[áa]n?\s+obligad[oa]s?\s+a\b", "must", "es_obligado", False),
    (r"\bes\s+obligatorio\b", "must", "es_obligatorio", False),
    (r"\btiene\s+que\b", "must", "es_tiene_que", False),
    (r"\btienen\s+que\b", "must", "es_tienen_que", False),
    (r"\bha\s+de\b", "must", "es_ha_de", False),
    (r"\bhan\s+de\b", "must", "es_han_de", False),
    (
        r"\b(?:debe|deber[áa]|deber[áa]n|deben|deber[íi]a\s+obligatoriamente)\b",
        "must",
        "es_debe",
        False,
    ),
    # -- permission --------------------------------------------------------
    (r"\b(?:is|are)\s+permitted\s+to\b", "may", "permitted_to", False),
    (r"\b(?:is|are)\s+allowed\s+to\b", "may", "allowed_to", False),
    (r"\b(?:is|are)\s+(?:authorised|authorized)\s+to\b", "may", "authorised_to", False),
    (r"\b(?:is|are)\s+entitled\s+to\b", "may", "entitled_to", False),
    (r"\b(?:is|are)\s+free\s+to\b", "may", "free_to", False),
    (r"\bha(?:s|ve)\s+the\s+right\s+to\b", "may", "right_to", False),
    (r"\bmay\b", "may", "may", False),
    (r"\bcan\b", "may", "can", True),
    (r"\bse\s+permite\b", "may", "es_se_permite", False),
    (r"\best[áa]\s+permitido\b", "may", "es_esta_permitido", False),
    (r"\b(?:est[áa]|est[áa]n)\s+autorizad[oa]s?\s+a\b", "may", "es_autorizado", False),
    (r"\btiene\s+derecho\s+a\b", "may", "es_derecho", False),
    (r"\btienen\s+derecho\s+a\b", "may", "es_derechos", False),
    (r"\b(?:puede|podr[áa]|podr[áa]n|pueden)\b", "may", "es_puede", False),
    # -- recommendation ----------------------------------------------------
    (r"\b(?:is|are)\s+recommended\s+to\b", "should", "recommended_to", False),
    (r"\bit\s+is\s+recommended\s+that\b", "should", "recommended_that", False),
    (r"\b(?:is|are)\s+advised\s+to\b", "should", "advised_to", False),
    (r"\b(?:is|are)\s+encouraged\s+to\b", "should", "encouraged_to", False),
    (r"\b(?:is|are)\s+expected\s+to\b", "should", "expected_to", True),
    (r"\bought\s+to\b", "should", "ought_to", False),
    (r"\bshould\b", "should", "should", False),
    (r"\bse\s+recomienda\b", "should", "es_se_recomienda", False),
    (r"\b(?:es|son)\s+recomendable\b", "should", "es_recomendable", False),
    (r"\b(?:deber[íi]a|deber[íi]an)\b", "should", "es_deberia", False),
)

NEGATIVE_FORMS: Final[frozenset[str]] = frozenset(
    {
        "should_not",
        "shouldnt",
        "ought_not",
        "not_recommended_to",
        "discouraged",
        "es_no_deberia",
        "es_no_se_recomienda",
    }
)
"""Form ids that express a *negative* recommendation.

The frozen ``Polarity`` enum has no ``SHOULD_NOT``.  Rather than silently
promoting these to ``MUST_NOT`` (which overstates the instrument) or dropping
the negation (which inverts it), they are emitted as ``SHOULD`` with
``direction=negative`` in ``attrs`` and a ``normalised`` value of
``should:negative``.
"""

# Second negation inside the governed clause turns "shall not be prohibited"
# into a permission.  We do not try to resolve that; we mark it uncertain.
DOUBLE_NEGATION_HEADS: Final[tuple[str, ...]] = (
    r"\bnot\b",
    r"\bno\b",
    r"\bnever\b",
    r"\bprohibit\w*",
    r"\bprevent\w*",
    r"\bpreclude\w*",
    r"\brestrict\w*\s+from\b",
    r"\bproh[íi]b\w*",
    r"\bimpid\w*",
    # "may not be required to" is an exemption wearing a prohibition's clothes.
    r"\bbe\s+(?:required|obliged|obligated|compelled)\b",
    r"\bser\s+(?:obligad\w*|requerid\w*)\b",
)

SCOPE_HEDGES: Final[tuple[tuple[str, str], ...]] = (
    (r"\bnothing\s+in\b", "nothing_in"),
    (r"\bwithout\s+prejudice\s+to\b", "without_prejudice"),
    (r"\bnotwithstanding\b", "notwithstanding"),
    (r"\bexcept\s+as\s+(?:otherwise\s+)?provided\b", "except_as_provided"),
    (r"\bsin\s+perjuicio\s+de\b", "sin_perjuicio"),
    (r"\bnada\s+de\s+lo\s+dispuesto\b", "nada_dispuesto"),
    # Epistemic frames: the sentence is about whether a duty exists, not an
    # assertion that it does.  Kept deliberately short — "the guidance states
    # that the firm must ..." is a real obligation and must not be hedged away.
    (r"\b(?:unclear|uncertain|not\s+clear)\b", "epistemic_uncertainty"),
    (r"\bwhether\b", "embedded_question"),
    (r"\b(?:allegedly|arguably|reportedly)\b", "attributed"),
    (r"\b(?:no\s+est[\u00e1a]\s+claro|se\s+desconoce)\b", "es_epistemic"),
)
"""Constructions that move the scope of a modal somewhere we cannot follow.

Each entry is (regex source, reason name).  A hit sets ``scope_uncertain`` on
the fact and the matcher reports UNCHECKABLE rather than asserting a polarity
it cannot stand behind."""

# ---------------------------------------------------------------------------
# Conditionals
# ---------------------------------------------------------------------------

CONDITIONAL_MARKERS: Final[tuple[tuple[str, str], ...]] = (
    (r"\bprovided\s+that\b", "provided_that"),
    (r"\bin\s+the\s+event\s+that\b", "in_the_event_that"),
    (r"\bsubject\s+to\b", "subject_to"),
    (r"\bunless\b", "unless"),
    (r"\bexcept\s+where\b", "except_where"),
    (r"\bif\b", "if"),
    (r"\bwhere\b", "where"),
    (r"\bwhenever\b", "whenever"),
    (r"\bwhen\b", "when"),
    (r"\bupon\b", "upon"),
    (r"\bsiempre\s+que\b", "siempre_que"),
    (r"\ba\s+menos\s+que\b", "a_menos_que"),
    (r"\bsalvo\s+que\b", "salvo_que"),
    (r"\bsalvo\b", "salvo"),
    (r"\ben\s+caso\s+de\s+que\b", "en_caso_de_que"),
    (r"\bcuando\b", "cuando"),
    (r"\bsi\b", "si"),
)

# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

MONTHS: Final[dict[str, int]] = {
    # English
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
    # Spanish
    "enero": 1,
    "ene": 1,
    "febrero": 2,
    "febr": 2,
    "marzo": 3,
    "abril": 4,
    "abr": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "ago": 8,
    "septiembre": 9,
    "setiembre": 9,
    "set": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
    "dic": 12,
}

DURATION_UNITS: Final[dict[str, str]] = {
    # English
    "second": "S",
    "seconds": "S",
    "sec": "S",
    "secs": "S",
    "minute": "M_T",
    "minutes": "M_T",
    "min": "M_T",
    "mins": "M_T",
    "hour": "H",
    "hours": "H",
    "hr": "H",
    "hrs": "H",
    "day": "D",
    "days": "D",
    "week": "W",
    "weeks": "W",
    "fortnight": "FORTNIGHT",
    "fortnights": "FORTNIGHT",
    "month": "M",
    "months": "M",
    "quarter": "Q",
    "quarters": "Q",
    "year": "Y",
    "years": "Y",
    # Spanish
    "segundo": "S",
    "segundos": "S",
    "minuto": "M_T",
    "minutos": "M_T",
    "hora": "H",
    "horas": "H",
    "dia": "D",
    "dias": "D",
    "día": "D",
    "días": "D",
    "semana": "W",
    "semanas": "W",
    "mes": "M",
    "meses": "M",
    "trimestre": "Q",
    "trimestres": "Q",
    "año": "Y",
    "años": "Y",
    "ano": "Y",
    "anos": "Y",
}

BUSINESS_DAY_QUALIFIERS: Final[tuple[str, ...]] = (
    "business",
    "working",
    "trading",
    "clear",
    "hábiles",
    "habiles",
    "hábil",
    "habil",
    "laborables",
    "laborable",
)

CALENDAR_DAY_QUALIFIERS: Final[tuple[str, ...]] = (
    "calendar",
    "naturales",
    "natural",
    "consecutive",
    "consecutivos",
)

POSTFIX_DAY_QUALIFIERS: Final[tuple[str, ...]] = (
    "hábiles",
    "habiles",
    "hábil",
    "habil",
    "laborables",
    "laborable",
    "naturales",
    "natural",
    "consecutivos",
)
"""Qualifiers that follow the unit rather than precede it (Spanish word order).

Kept separate from the English ones on purpose: allowing any qualifier to
trail would make "10 days working on the project" a business-day duration.
"""

# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

CURRENCY_SYMBOLS: Final[dict[str, str]] = {
    "\u20ac": "EUR",
    "\u00a3": "GBP",
    "US$": "USD",
    "R$": "BRL",
    "\u20b9": "INR",
    "\u20a9": "KRW",
    "\u20ba": "TRY",
    "\u20bd": "RUB",
    "z\u0142": "PLN",
    "K\u010d": "CZK",
}
"""Currency markers that resolve to exactly one ISO 4217 code."""

AMBIGUOUS_MARKERS: Final[dict[str, frozenset[str]]] = {
    "$": frozenset({"USD", "CAD", "AUD", "NZD", "MXN", "ARS", "CLP", "COP", "SGD", "HKD", "BRL"}),
    "\u00a5": frozenset({"JPY", "CNY"}),
    "kr": frozenset({"SEK", "NOK", "DKK", "ISK"}),
    "dollar": frozenset({"USD", "CAD", "AUD", "NZD", "SGD", "HKD"}),
    "dollars": frozenset({"USD", "CAD", "AUD", "NZD", "SGD", "HKD"}),
    "d\u00f3lar": frozenset({"USD", "CAD", "AUD", "MXN", "ARS", "CLP", "COP"}),
    "d\u00f3lares": frozenset({"USD", "CAD", "AUD", "MXN", "ARS", "CLP", "COP"}),
    "dolar": frozenset({"USD", "CAD", "AUD", "MXN", "ARS", "CLP", "COP"}),
    "dolares": frozenset({"USD", "CAD", "AUD", "MXN", "ARS", "CLP", "COP"}),
    "peso": frozenset({"MXN", "ARS", "CLP", "COP", "PEN"}),
    "pesos": frozenset({"MXN", "ARS", "CLP", "COP", "PEN"}),
    "corona": frozenset({"SEK", "NOK", "DKK", "ISK"}),
    "coronas": frozenset({"SEK", "NOK", "DKK", "ISK"}),
    "krona": frozenset({"SEK", "ISK"}),
    "kronor": frozenset({"SEK"}),
    "krone": frozenset({"NOK", "DKK"}),
}
"""Markers that name a family of currencies.

Resolved to the locale profile's declared currency only when that currency is
in the family.  Otherwise the marker is kept verbatim and flagged: a dollar
sign in a document written under a euro profile is not a euro, and it is not
the extractor's business to decide which dollar it is.
"""

CURRENCY_CODES: Final[frozenset[str]] = frozenset(
    {
        "EUR",
        "USD",
        "GBP",
        "CHF",
        "JPY",
        "CNY",
        "SEK",
        "NOK",
        "DKK",
        "PLN",
        "CZK",
        "HUF",
        "RON",
        "BGN",
        "HRK",
        "ISK",
        "TRY",
        "RUB",
        "CAD",
        "AUD",
        "NZD",
        "MXN",
        "BRL",
        "ARS",
        "CLP",
        "COP",
        "PEN",
        "INR",
        "KRW",
        "SGD",
        "HKD",
        "ZAR",
        "AED",
        "SAR",
        "ILS",
        "THB",
        "MYR",
        "IDR",
        "PHP",
        "VND",
    }
)

CURRENCY_WORDS: Final[dict[str, str]] = {
    "euro": "EUR",
    "euros": "EUR",
    "pound": "GBP",
    "pounds": "GBP",
    "sterling": "GBP",
    "libra": "GBP",
    "libras": "GBP",
    "yen": "JPY",
    "yenes": "JPY",
    "franc": "CHF",
    "francs": "CHF",
    "franco": "CHF",
    "francos": "CHF",
    "zloty": "PLN",
    "zlotys": "PLN",
    "rupee": "INR",
    "rupees": "INR",
    "rupia": "INR",
    "rupias": "INR",
}

MULTIPLIERS: Final[dict[str, str]] = {
    # token -> decimal multiplier as a string (Decimal-parsed, never float)
    "k": "1000",
    "thousand": "1000",
    "thousands": "1000",
    "mil": "1000",
    "m": "1000000",
    "mm": "1000000",
    "million": "1000000",
    "millions": "1000000",
    "millon": "1000000",
    "millón": "1000000",
    "millones": "1000000",
    "bn": "1000000000",
    "billion": "1000000000",
    "billions": "1000000000",
    "tn": "1000000000000",
    "trillion": "1000000000000",
}

AMBIGUOUS_MULTIPLIERS: Final[frozenset[str]] = frozenset({"billon", "billón", "billones"})
"""Spanish ``billón`` is 10**12, but is very often written meaning 10**9."""

# ---------------------------------------------------------------------------
# Stopwords (context and predicate keys only — never used for value matching)
# ---------------------------------------------------------------------------

STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        # English
        "the",
        "and",
        "for",
        "that",
        "this",
        "with",
        "from",
        "has",
        "have",
        "had",
        "are",
        "was",
        "were",
        "been",
        "being",
        "its",
        "it's",
        "any",
        "all",
        "such",
        "not",
        "but",
        "you",
        "your",
        "our",
        "their",
        "they",
        "them",
        "his",
        "her",
        "will",
        "would",
        "can",
        "could",
        "may",
        "might",
        "must",
        "should",
        "into",
        "onto",
        "than",
        "then",
        "there",
        "these",
        "those",
        "which",
        "who",
        "whom",
        "whose",
        "what",
        "when",
        "where",
        "while",
        "about",
        "above",
        "after",
        "before",
        "between",
        "under",
        "over",
        "each",
        "other",
        "some",
        "only",
        "own",
        "same",
        "also",
        "very",
        "per",
        "via",
        "upon",
        "shall",
        "does",
        "did",
        "doing",
        # Spanish
        "que",
        "los",
        "las",
        "del",
        "por",
        "con",
        "para",
        "una",
        "unos",
        "unas",
        "como",
        "más",
        "mas",
        "pero",
        "sus",
        "les",
        "esta",
        "este",
        "estos",
        "estas",
        "son",
        "ser",
        "está",
        "estan",
        "están",
        "sido",
        "haber",
        "hay",
        "sin",
        "sobre",
        "entre",
        "cuando",
        "donde",
        "todo",
        "todos",
        "toda",
        "todas",
        "debe",
        "deberá",
        "podrá",
        "puede",
        "pueden",
        "debera",
        "podra",
    }
)
