#!/usr/bin/env python3
"""
Multiple-choice reformulation of the LLM abbreviation-expansion step.

Instead of asking the model to rewrite the whole text (which risks corrupting
words it should not touch), each abbreviation occurrence that has glossary
candidates is marked in the text as [[id|abbreviation]] and the model only
returns a JSON object mapping id -> chosen candidate. The substitution itself
happens programmatically, so:
- the surrounding text cannot be corrupted,
- only listed abbreviations can change,
- validating a choice is a simple membership test instead of a token diff.

The chosen candidates are inserted in their base (dictionary) form; adjusting
the grammatical form is left to the normalisation step.
"""

import json
import re
from dataclasses import dataclass


@dataclass
class Occurrence:
    """One occurrence of an abbreviation with candidates in a text."""

    id: int
    abbreviation: str  # key into the candidates dict
    matched: str  # exact matched text (spacing may differ from the key)
    start: int
    end: int


def occurrence_pattern(abbreviation: str) -> str:
    """
    Regex for one abbreviation, with the spaces between its parts optional
    (same convention as the replacement rules in expansion_simple.ipynb).
    """
    return r"\b" + re.escape(abbreviation).replace(r"\ ", r"[ \t]*")


def find_candidate_occurrences(
    text: str, candidates: dict[str, list[str]]
) -> list[Occurrence]:
    """
    Locate all occurrences of the candidate abbreviations in the text.

    Overlapping matches are resolved in favour of the longer one (e.g. inside
    `abb. et conv.` neither `abb.` nor `conv.` is reported separately), so a
    multi-word abbreviation is never split into its parts. Occurrences are
    numbered left to right, starting at 1.
    """
    matches = []
    for abbr in candidates:
        for m in re.finditer(occurrence_pattern(abbr), text):
            matches.append((m.start(), m.end(), abbr, m.group(0)))

    # sort by position, longer matches first, so the greedy pass below keeps
    # the longest match of any overlapping group (and drops duplicates coming
    # from spacing variants of the same abbreviation)
    matches.sort(key=lambda match: (match[0], -(match[1] - match[0])))

    occurrences = []
    last_end = 0
    for start, end, abbr, matched in matches:
        if start < last_end:
            continue
        occurrences.append(
            Occurrence(
                id=len(occurrences) + 1,
                abbreviation=abbr,
                matched=matched,
                start=start,
                end=end,
            )
        )
        last_end = end

    return occurrences


def mark_text(text: str, occurrences: list[Occurrence]) -> str:
    """Replace every occurrence with its [[id|abbreviation]] marker."""
    parts = []
    pos = 0
    for occ in occurrences:
        parts.append(text[pos : occ.start])
        parts.append(f"[[{occ.id}|{occ.matched}]]")
        pos = occ.end
    parts.append(text[pos:])
    return "".join(parts)


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
        "Here are the expansion candidates for each marked abbreviation:",
    ]
    for occ in occurrences:
        cands = candidates[occ.abbreviation]
        lines.append(
            f"- [[{occ.id}]] `{occ.matched}`: {', '.join(f'`{c}`' for c in cands)}"
        )
    lines += [
        "",
        "Return a JSON object mapping every id to the chosen candidate.",
    ]
    return "\n".join(lines)


def parse_choices(
    content: str, occurrences: list[Occurrence], candidates: dict[str, list[str]]
) -> tuple[dict[int, str] | None, list[dict]]:
    """
    Parse the model response into a mapping id -> chosen candidate.

    Returns (choices, errors). choices is None if no JSON object could be
    parsed at all (the caller may retry); otherwise every id whose choice is
    missing or not among the candidates is reported in errors and simply left
    out of choices (i.e. left unexpanded).
    """
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end < start:
        return None, [{"message": "No JSON object found in model response"}]
    try:
        raw = json.loads(content[start : end + 1])
    except json.JSONDecodeError as e:
        return None, [{"message": f"Model response is not valid JSON: {e}"}]
    if not isinstance(raw, dict):
        return None, [{"message": "Model response is not a JSON object"}]

    errors = []
    choices: dict[int, str] = {}
    for occ in occurrences:
        value = raw.get(str(occ.id))
        if value is None:
            errors.append(
                {
                    "id": occ.id,
                    "message": f"Missing choice: no candidate chosen for [[{occ.id}]] '{occ.matched}'",
                }
            )
            continue
        value = str(value).strip().strip("`")
        if value not in candidates[occ.abbreviation]:
            errors.append(
                {
                    "id": occ.id,
                    "message": (
                        f"Invalid choice: [[{occ.id}]] '{occ.matched}' → '{value}' "
                        f"(not in allowed candidates)"
                    ),
                }
            )
            continue
        choices[occ.id] = value

    known_ids = {str(occ.id) for occ in occurrences}
    for key in raw:
        if str(key) not in known_ids:
            errors.append(
                {
                    "id": key,
                    "message": f"Unknown id: choice for '{key}' ignored",
                }
            )

    return choices, errors


def apply_choices(
    text: str, occurrences: list[Occurrence], choices: dict[int, str]
) -> str:
    """
    Substitute the chosen candidates into the text. Occurrences without a
    (valid) choice keep their original abbreviation.
    """
    parts = []
    pos = 0
    for occ in occurrences:
        parts.append(text[pos : occ.start])
        parts.append(choices.get(occ.id, occ.matched))
        pos = occ.end
    parts.append(text[pos:])
    return "".join(parts)
