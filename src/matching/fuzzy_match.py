"""Fuzzy matching of OCR text to the medicines knowledge base (RapidFuzz)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence, Union

from rapidfuzz import fuzz, process

import config

Medicine = dict[str, Any]
_STOP = {"tablet", "tablets", "capsule", "capsules", "syrup", "film", "coated", "each", "contains",
         "store", "below", "keep", "reach", "children", "batch", "price", "retail", "made", "pakistan",
         "mfg", "exp", "date", "the", "and", "for", "use", "only", "pack", "strip", "box"}


@dataclass(frozen=True)
class MatchResult:
    """One candidate medicine with a 0-100 confidence score."""

    medicine_id: int
    brand_name: str
    generic_name: str
    score: float
    matched_on: str   # "brand", "generic" or "brand (first word)"
    matched_text: str  # the OCR fragment that produced the score
    meets_threshold: bool


def normalize_text(text: str) -> str:
    """Lower-case, fix digit/letter confusion inside words, strip punctuation, collapse spaces."""
    words = []
    for token in re.split(r"[^a-z0-9]+", (text or "").lower()):
        if not token:
            continue
        letters = sum(c.isalpha() for c in token)
        if letters >= 2 and any(c.isdigit() for c in token):
            token = token.replace("0", "o").replace("1", "l").replace("5", "s")
        words.append(token)
    return " ".join(words)


def build_candidates(lines: Union[str, Iterable[str]], max_ngram: int = 4) -> list[str]:
    """Build unique candidate strings from OCR lines: whole lines, words and word n-grams."""
    if isinstance(lines, str):
        lines = lines.splitlines() or [lines]
    out: dict[str, None] = {}
    for line in lines:
        norm = normalize_text(line)
        if not norm:
            continue
        words = norm.split()
        if len(norm) >= 3:
            out[norm] = None
        for n in range(1, max_ngram + 1):
            for i in range(len(words) - n + 1):
                gram = " ".join(words[i:i + n])
                if n == 1 and (len(gram) < 3 or gram in _STOP or gram.isdigit()):
                    continue
                if len(gram) >= 3:
                    out[gram] = None
    return list(out)


def _name_variants(med: Medicine) -> list[tuple[str, float, str]]:
    brand = normalize_text(med["brand_name"])
    variants = [(brand, 1.0, "brand"), (normalize_text(med["generic_name"]), 0.95, "generic")]
    first = brand.split()[0] if brand else ""
    if " " in brand and len(first) >= 3:
        variants.append((first, 0.85, "brand (first word)"))
    return [v for v in variants if v[0]]


def score_medicine(med: Medicine, candidates: Sequence[str]) -> tuple[float, str, str]:
    """Best (score, matched_on, matched_text) of a medicine against the candidate strings."""
    best = (0.0, "", "")
    for name, weight, kind in _name_variants(med):
        found = process.extractOne(name, candidates, scorer=fuzz.ratio)
        if not found:
            continue
        text, raw, _ = found
        score = raw * weight
        if len(name) <= 4 and raw < 90:  # very short names need a near-exact hit
            score *= 0.7
        if score > best[0]:
            best = (score, kind, text)
    return best


def match_medicine(
    lines: Union[str, Iterable[str]], medicines: Sequence[Medicine],
    top_k: int = config.TOP_K_MATCHES, threshold: float = config.MATCH_CONFIDENCE_THRESHOLD,
) -> list[MatchResult]:
    """Return the ``top_k`` best matches (highest first); each flags ``meets_threshold``."""
    candidates = build_candidates(lines)
    if not candidates:
        return []
    results = []
    for med in medicines:
        score, kind, text = score_medicine(med, candidates)
        if score > 0:
            results.append(MatchResult(
                medicine_id=int(med["id"]), brand_name=med["brand_name"],
                generic_name=med["generic_name"], score=round(score, 1), matched_on=kind,
                matched_text=text, meets_threshold=score >= threshold))
    # On equal scores: brand beats generic, then the longer (more specific) matched fragment wins.
    results.sort(key=lambda r: (-r.score, r.matched_on != "brand", -len(r.matched_text), r.brand_name))
    return results[:top_k]


def search_medicines(query: str, medicines: Sequence[Medicine], limit: int = 10) -> list[Medicine]:
    """Manual search: substring hits first, then fuzzy matches on brand/generic/ingredient."""
    q = normalize_text(query)
    if not q:
        return []
    scored: dict[int, float] = {}
    for med in medicines:
        fields = [normalize_text(med[k]) for k in ("brand_name", "generic_name", "active_ingredient")]
        if any(q in f for f in fields):
            scored[med["id"]] = 100.0 if fields[0].startswith(q) else 90.0
        else:
            best = max(fuzz.WRatio(q, f) for f in fields if f)
            if best >= 75:
                scored[med["id"]] = best * 0.8
    by_id = {m["id"]: m for m in medicines}
    ranked = sorted(scored, key=lambda i: (-scored[i], by_id[i]["brand_name"]))
    return [by_id[i] for i in ranked[:limit]]
