#!/usr/bin/env python3
"""
Step 3: expanding the abbreviations that have no glossary entry.

Uses the same approach as the multiple-choice step (multiple_choice.py):
occurrences are marked in the text as [[id|abbreviation]], the model returns
only a JSON object mapping each id to its expansion, and the substitution
happens programmatically, so the surrounding text cannot be corrupted.

Because there are no curated candidates, two other safeguards replace the
candidate-membership check:

1. **Corpus-mined suggestions**: words that appear unabbreviated in the RG
   and share the abbreviation's prefix are offered to the model, ranked by
   frequency. They are surface forms, so the model can pick an already
   correctly inflected word.
2. **Truncation constraint**: these abbreviations are cut-off words, so any
   expansion (suggested or free) must begin with the letters of the
   abbreviation itself. A doubled final consonant (eccll., diocc.) marks a
   plural and is allowed to collapse (eccll. -> ecclesie). Expansions that
   violate the constraint are rejected and the abbreviation is kept.

The model may also answer "SKIP" for tokens that are not really abbreviations
(e.g. a word before a sentence-final period) or that it cannot expand with
confidence; those keep their abbreviation.
"""

import json
import re
from bisect import bisect_left
from collections import Counter

from multiple_choice import Occurrence, apply_choices, mark_text

# tokens that look like abbreviations but should not be sent to the model:
# pure numbers ("26.") never match (letters only), Roman numerals
# ("XXIII.") and single letters ("B.") are filtered explicitly
TOKEN = re.compile(r"\b([A-Za-z]{2,})\.")
ROMAN = re.compile(r"^[IVXLCDM]+$")


def find_remaining_occurrences(text: str) -> list[Occurrence]:
    """All abbreviation-like tokens worth attempting, numbered left to right."""
    occurrences = []
    for m in TOKEN.finditer(text):
        if ROMAN.match(m.group(1)):
            continue
        occurrences.append(
            Occurrence(
                id=len(occurrences) + 1,
                abbreviation=m.group(0),
                matched=m.group(0),
                start=m.start(),
                end=m.end(),
            )
        )
    return occurrences


class Vocabulary:
    """Corpus vocabulary with fast prefix lookup."""

    def __init__(self, counts: Counter):
        self.counts = counts
        self.words = sorted(counts)

    @classmethod
    def from_texts(cls, texts, min_length: int = 3) -> "Vocabulary":
        counts: Counter = Counter()
        # only words NOT followed by a period, i.e. not themselves abbreviated
        pattern = re.compile(rf"\b([A-Za-z]{{{min_length},}})\b(?!\.)")
        for text in texts:
            if text:
                counts.update(pattern.findall(text))
        return cls(counts)

    def with_prefix(self, prefix: str) -> list[tuple[str, int]]:
        start = bisect_left(self.words, prefix)
        end = bisect_left(self.words, prefix + "￿")
        return [(w, self.counts[w]) for w in self.words[start:end]]


def abbreviation_prefixes(abbreviation: str) -> list[str]:
    """
    Prefixes an expansion may start with. A doubled final consonant marks a
    plural (eccll. -> ecclesie), so the collapsed prefix is allowed too.
    """
    stem = abbreviation.rstrip(".")
    prefixes = [stem]
    if len(stem) >= 2 and stem[-1] == stem[-2]:
        prefixes.append(stem[:-1])
    return prefixes


def mine_candidates(
    occurrences: list[Occurrence],
    vocabulary: Vocabulary,
    max_candidates: int = 10,
    min_count: int = 2,
) -> dict[str, list[str]]:
    """Frequency-ranked corpus words sharing each abbreviation's prefix."""
    candidates: dict[str, list[str]] = {}
    for occ in occurrences:
        if occ.abbreviation in candidates:
            continue
        found: dict[str, int] = {}
        for prefix in abbreviation_prefixes(occ.abbreviation):
            for word, count in vocabulary.with_prefix(prefix):
                if len(word) > len(prefix) and count >= min_count:
                    found[word] = count
        ranked = sorted(found.items(), key=lambda item: -item[1])
        candidates[occ.abbreviation] = [w for w, _ in ranked[:max_candidates]]
    return candidates


def build_user_prompt(
    text: str, occurrences: list[Occurrence], candidates: dict[str, list[str]]
) -> str:
    marked = mark_text(text, occurrences)

    lines = [
        "Here is the Latin text with the abbreviations marked as [[id|abbreviation]]:",
        "```",
        marked,
        "```",
        "",
        "Corpus words sharing each abbreviation's prefix (possibly incomplete or misleading):",
    ]
    for occ in occurrences:
        cands = candidates.get(occ.abbreviation) or []
        suggestions = ", ".join(f"`{c}`" for c in cands) if cands else "(none)"
        lines.append(f"- [[{occ.id}]] `{occ.matched}`: {suggestions}")
    lines += [
        "",
        'Return a JSON object mapping every id to its expansion (a single Latin word) or "SKIP".',
    ]
    return "\n".join(lines)


def valid_expansion(abbreviation: str, expansion: str) -> bool:
    """A free expansion must be one word and extend the abbreviation."""
    if not expansion.isalpha():
        return False
    return any(
        expansion.startswith(p) and len(expansion) > len(p)
        for p in abbreviation_prefixes(abbreviation)
    )


def parse_expansions(
    content: str, occurrences: list[Occurrence], candidates: dict[str, list[str]]
) -> tuple[dict[int, str] | None, list[dict], list[dict]]:
    """
    Parse the model response.

    Returns (choices, details, errors):
    - choices: id -> accepted expansion (missing ids keep their abbreviation)
    - details: one record per id with the acceptance tier:
        "suggestion" (was among the corpus suggestions),
        "free" (novel but satisfies the truncation constraint),
        "skip" (model declined), "rejected", "missing"
    - errors: rejected/missing/unknown ids with messages
    choices is None if no JSON object could be parsed at all.
    """
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end < start:
        return None, [], [{"message": "No JSON object found in model response"}]
    try:
        raw = json.loads(content[start : end + 1])
    except json.JSONDecodeError as e:
        return None, [], [{"message": f"Model response is not valid JSON: {e}"}]
    if not isinstance(raw, dict):
        return None, [], [{"message": "Model response is not a JSON object"}]

    choices: dict[int, str] = {}
    details: list[dict] = []
    errors: list[dict] = []

    for occ in occurrences:
        value = raw.get(str(occ.id))
        record = {"id": occ.id, "abbreviation": occ.matched, "expansion": None}
        if value is None:
            record["tier"] = "missing"
            errors.append(
                {
                    "id": occ.id,
                    "message": f"Missing expansion: nothing returned for [[{occ.id}]] '{occ.matched}'",
                }
            )
        else:
            value = str(value).strip().strip("`")
            if value.upper() == "SKIP":
                record["tier"] = "skip"
            elif value in (candidates.get(occ.abbreviation) or []):
                record["tier"] = "suggestion"
                record["expansion"] = value
                choices[occ.id] = value
            elif valid_expansion(occ.abbreviation, value):
                record["tier"] = "free"
                record["expansion"] = value
                choices[occ.id] = value
            else:
                record["tier"] = "rejected"
                errors.append(
                    {
                        "id": occ.id,
                        "message": (
                            f"Rejected expansion: [[{occ.id}]] '{occ.matched}' → '{value}' "
                            f"(does not extend the abbreviation)"
                        ),
                    }
                )
        details.append(record)

    known_ids = {str(occ.id) for occ in occurrences}
    for key in raw:
        if str(key) not in known_ids:
            errors.append(
                {"id": key, "message": f"Unknown id: expansion for '{key}' ignored"}
            )

    return choices, details, errors
