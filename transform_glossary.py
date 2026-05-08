#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Transform a raw abbreviation glossary CSV into a structured, volume-aware lexical database.

Outputs:
- glossary_rows_normalized.csv
- lexical_entries.csv
- aliases.csv
- manual_review.csv
- lexical_db.json

Design goals:
- deterministic
- conservative
- transparent heuristics
- high reproducibility

Usage:
    python transform_glossary.py input.csv output_dir
"""

import csv
import json
import os
import re
import sys
from copy import deepcopy

RG_COLUMNS = [f"RG{i}" for i in range(1, 10)]

EXPECTED_COLUMNS = [
    "Abkürzung", "Auflösung", "Übersetzung", "Anmerkungen",
    "Wortstamm", "Deklination",
    "RG1", "RG2", "RG3", "RG4", "RG5", "RG6", "RG7", "RG8", "RG9",
    "Bemerkungen", "Bemerkungen"
]

# TODO are any entries missed that would be found by simply searching for "siehe"?
SEE_RE = re.compile(r'^\s*siehe\s+(.+?)\s*\.?\s*$', re.IGNORECASE)
QUESTION_RE = re.compile(r'\?')
PAREN_RE = re.compile(r'^(.*?)\s*$([^()]*)$\s*$')
DEF_NAT_HELPER_RE = re.compile(r'^\s*$nur bei def\. nat\.:$\s*(.+)$', re.IGNORECASE)

MULTISPACE_RE = re.compile(r'\s+')
SEMICOLON_SPLIT_RE = re.compile(r'\s*;\s*')

WARNING_PATTERNS = {
    "uncertain": re.compile(r'\b(möglicherweise|wohl|nicht sicher|fraglich|zweifelhaft)\b', re.IGNORECASE),
    "unknown": re.compile(r'\?', re.IGNORECASE),
    "inexistent": re.compile(r'\binexistent\b', re.IGNORECASE),
    "not_checked": re.compile(r'(nicht nachzuprüfen|zu viel zum überprüfen|zu viele Treffer)', re.IGNORECASE),
    "volume_specific": re.compile(r'\b(in Bd\.|laut Abk\-Verz\.|nur in \d|Bd\. \d)\b', re.IGNORECASE),
    "crossref": re.compile(r'^\s*siehe\s+', re.IGNORECASE),
    "only_once": re.compile(r'(nur einmal verwendet|jeweils einmal)', re.IGNORECASE),
    "written_out_also": re.compile(r'(auch .* ausgeschrieben|kommt auch .* vor|ausgeschrieben)', re.IGNORECASE),
}

def normalize_whitespace(s):
    if s is None:
        return ""
    return MULTISPACE_RE.sub(" ", s.strip())

def normalize_abbr(s):
    s = normalize_whitespace(s)
    # preserve punctuation; only normalize spacing
    return s

def contains_phrase_level(abbr):
    if not abbr:
        return False
    # multiple tokens or multiple dotted components
    return (" " in abbr.strip()) or (abbr.count(".") > 1)

def detect_crossref(text):
    if not text:
        return None
    m = SEE_RE.match(text)
    if m:
        return normalize_whitespace(m.group(1))
    return None

def extract_parenthetical(expansion):
    """
    Returns:
        expansion_main, editorial_note
    Only strips a final (...) pattern conservatively.
    """
    if not expansion:
        return expansion, ""
    m = PAREN_RE.match(expansion.strip())
    if m:
        main = normalize_whitespace(m.group(1))
        note = normalize_whitespace(m.group(2))
        return main, note
    return normalize_whitespace(expansion), ""

def split_expansion_candidates(expansion):
    """
    Conservative split on semicolons only.
    Keeps things reproducible and easy to audit.
    """
    if not expansion:
        return []
    parts = [normalize_whitespace(p) for p in SEMICOLON_SPLIT_RE.split(expansion) if normalize_whitespace(p)]
    return parts if parts else [normalize_whitespace(expansion)]

def gather_warning_flags(*texts):
    flags = set()
    merged = " | ".join([t for t in texts if t])
    for key, pattern in WARNING_PATTERNS.items():
        if pattern.search(merged):
            flags.add(key)
    return sorted(flags)

def provisional_class(record):
    """
    Conservative provisional classification.
    """
    abbr = record.get("abbr_norm", "")
    expansion = record.get("expansion_raw", "")
    notes = record.get("notes_merged", "")
    crossref = record.get("crossref_target_raw", "")
    warnings = set(record.get("warning_flags", []))

    # TODO shouldn't "unsafe_manual" have a higher priority?
    if crossref:
        return "ALIAS_CROSSREF"

    if not abbr and not expansion:
        return "UNSAFE_MANUAL"

    if "unknown" in warnings or "inexistent" in warnings:
        return "UNSAFE_MANUAL"

    # TODO obsolete?
    if record.get("editorial_only_helper", False):
        return "EDITORIAL_NOTE_ONLY"

    # TODO why EDITORIAL_NOTE_ONLY, when it's not necessarily **only** an editorial note?
    if record.get("contains_parentheses", False) and expansion:
        # often still a valid lexical row, but with editorial note
        # if highly formulaic and stable, downstream can upgrade
        return "EDITORIAL_NOTE_ONLY"

    # semicolon often signals ambiguity or multiple senses
    if ";" in expansion:
        return "LLM_CANDIDATE"

    if "volume_specific" in warnings:
        return "SAFE_RULE_IF_VOLUME"

    if len(abbr.strip()) <= 2 and "." in abbr:
        # very short abbreviations are often ambiguous
        return "LLM_CANDIDATE"

    return "SAFE_RULE"

def ensure_output_dir(path):
    os.makedirs(path, exist_ok=True)

def read_csv_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    return rows

def normalize_header(header):
    """
    Handles duplicate 'Bemerkungen' by renaming them.
    """
    out = []
    seen = {}
    for col in header:
        c = normalize_whitespace(col)
        seen[c] = seen.get(c, 0) + 1
        if seen[c] == 1:
            out.append(c)
        else:
            out.append(f"{c}_{seen[c]}")
    return out

def rows_to_dicts(rows):
    header = normalize_header(rows[0])
    dicts = []
    for i, row in enumerate(rows[1:], start=1):
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        elif len(row) > len(header):
            row = row[:len(header)]
        d = dict(zip(header, row))
        d["_source_row_num"] = i + 1  # physical CSV line number incl. header
        dicts.append(d)
    return dicts

def transform(input_csv, output_dir):
    ensure_output_dir(output_dir)

    raw_rows = rows_to_dicts(read_csv_rows(input_csv))

    normalized_rows = []
    lexical_entries = []
    aliases = []
    manual_review = []

    current_abbr_context = ""
    current_family_row_id = None

    for idx, row in enumerate(raw_rows, start=1):
        abbr_raw = normalize_whitespace(row.get("Abkürzung", ""))
        expansion_raw = normalize_whitespace(row.get("Auflösung", ""))
        translation_raw = normalize_whitespace(row.get("Übersetzung", ""))
        notes_raw = normalize_whitespace(row.get("Anmerkungen", ""))
        stem_raw = normalize_whitespace(row.get("Wortstamm", ""))
        decl_raw = normalize_whitespace(row.get("Deklination", ""))
        remarks_1 = normalize_whitespace(row.get("Bemerkungen", ""))
        remarks_2 = normalize_whitespace(row.get("Bemerkungen_2", ""))

        notes_merged = " | ".join([x for x in [notes_raw, remarks_1, remarks_2] if x])

        inherits_previous_abbr = False
        if abbr_raw:
            current_abbr_context = abbr_raw
            current_family_row_id = idx
        else:
            inherits_previous_abbr = True

        abbr_norm = normalize_abbr(abbr_raw if abbr_raw else current_abbr_context)

        crossref_target = detect_crossref(expansion_raw) or detect_crossref(notes_raw)

        # TODO why does this work correctly for "add. (ment.)" and not see (ment.) as an editorial note?
        expansion_main, editorial_note = extract_parenthetical(expansion_raw)
        contains_parentheses = bool(editorial_note)

        # TODO: can be removed, because "nur bei def. nat." isn't really a thing anymore? (revised the entries)
        helper_match = DEF_NAT_HELPER_RE.match(abbr_raw)
        editorial_only_helper = bool(helper_match)

        warning_flags = gather_warning_flags(expansion_raw, notes_raw, remarks_1, remarks_2)

        row_record = {
            "row_id": idx,
            "source_row_num": row["_source_row_num"],
            "family_row_id": current_family_row_id,
            "abbr_raw": abbr_raw,
            "abbr_norm": abbr_norm,
            "abbr_missing": not bool(abbr_raw),
            "inherits_previous_abbr": inherits_previous_abbr,
            "expansion_raw": expansion_raw,
            "expansion_main": expansion_main,
            "editorial_note": editorial_note,
            "translation_raw": translation_raw,
            "notes_raw": notes_raw,
            "notes_merged": notes_merged,
            "stem_raw": stem_raw,
            "declension_raw": decl_raw,
            "crossref_target_raw": crossref_target or "",
            "contains_question": bool(QUESTION_RE.search(expansion_raw + " " + notes_merged)),
            "contains_parentheses": contains_parentheses,
            "is_phrase_level": contains_phrase_level(abbr_norm),
            "editorial_only_helper": editorial_only_helper,
            "warning_flags": warning_flags,
        }

        for rg in RG_COLUMNS:
            row_record[rg.lower()] = normalize_whitespace(row.get(rg, ""))

        row_record["provisional_class"] = provisional_class(row_record)
        normalized_rows.append(row_record)

        # Build lexical entries conservatively
        if row_record["provisional_class"] == "ALIAS_CROSSREF":
            aliases.append({
                "alias_id": f"alias_{idx}",
                "source_row_id": idx,
                "alias_abbr": abbr_norm,
                "crossref_target_raw": crossref_target or "",
                "notes": notes_merged,
                "is_phrase_level": row_record["is_phrase_level"],
            })
            continue

        if row_record["provisional_class"] == "EDITORIAL_NOTE_ONLY":
            manual_review.append({
                "review_id": f"review_{idx}",
                "source_row_id": idx,
                "abbr": abbr_norm,
                "expansion_raw": expansion_raw,
                "reason": "editorial_note_only_or_parenthetical",
                "notes": notes_merged,
            })
            # still preserve as lexical if there is a clear main expansion
            if expansion_main:
                lexical_entries.append({
                    "entry_id": f"entry_{idx}_1",
                    "source_row_id": idx,
                    "canonical_abbr": abbr_norm,
                    "surface_abbr": abbr_raw if abbr_raw else abbr_norm,
                    "expansion_candidate": expansion_main,
                    "editorial_note": editorial_note,
                    "translation": translation_raw,
                    "class": "EDITORIAL_NOTE_ONLY",
                    "crossref_target": "",
                    "phrase_level": row_record["is_phrase_level"],
                    "volume_sensitive": "volume_specific" in warning_flags,
                    "needs_manual_review": True,
                    "warning_flags": "|".join(warning_flags),
                })
            continue

        if row_record["provisional_class"] == "UNSAFE_MANUAL":
            manual_review.append({
                "review_id": f"review_{idx}",
                "source_row_id": idx,
                "abbr": abbr_norm,
                "expansion_raw": expansion_raw,
                "reason": "unsafe_or_unknown",
                "notes": notes_merged,
            })
            continue

        candidates = split_expansion_candidates(expansion_main if expansion_main else expansion_raw)
        if not candidates:
            candidates = [""]

        for j, cand in enumerate(candidates, start=1):
            lexical_entries.append({
                "entry_id": f"entry_{idx}_{j}",
                "source_row_id": idx,
                "canonical_abbr": abbr_norm,
                "surface_abbr": abbr_raw if abbr_raw else abbr_norm,
                "expansion_candidate": cand,
                "editorial_note": editorial_note,
                "translation": translation_raw,
                "class": row_record["provisional_class"],
                "crossref_target": "",
                "phrase_level": row_record["is_phrase_level"],
                "volume_sensitive": "volume_specific" in warning_flags,
                "needs_manual_review": inherits_previous_abbr or (";" in expansion_raw),
                "warning_flags": "|".join(warning_flags),
            })

        if inherits_previous_abbr or row_record["contains_question"] or ("volume_specific" in warning_flags and ";" in expansion_raw):
            manual_review.append({
                "review_id": f"review_{idx}",
                "source_row_id": idx,
                "abbr": abbr_norm,
                "expansion_raw": expansion_raw,
                "reason": "inherited_abbr_or_complex_ambiguity",
                "notes": notes_merged,
            })

    # Write CSV outputs
    write_csv(
        os.path.join(output_dir, "glossary_rows_normalized.csv"),
        normalized_rows
    )
    write_csv(
        os.path.join(output_dir, "lexical_entries.csv"),
        lexical_entries
    )
    write_csv(
        os.path.join(output_dir, "aliases.csv"),
        aliases
    )
    write_csv(
        os.path.join(output_dir, "manual_review.csv"),
        manual_review
    )

    # JSON output
    lexical_db = {
        "metadata": {
            "source_csv": os.path.basename(input_csv),
            "row_count": len(normalized_rows),
            "lexical_entry_count": len(lexical_entries),
            "alias_count": len(aliases),
            "manual_review_count": len(manual_review),
        },
        "rows": normalized_rows,
        "lexical_entries": lexical_entries,
        "aliases": aliases,
        "manual_review": manual_review,
    }

    with open(os.path.join(output_dir, "lexical_db.json"), "w", encoding="utf-8") as f:
        json.dump(lexical_db, f, ensure_ascii=False, indent=2)

def write_csv(path, rows):
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def main():
    if len(sys.argv) != 3:
        print("Usage: python transform_glossary.py input.csv output_dir")
        sys.exit(1)
    input_csv = sys.argv[1]
    output_dir = sys.argv[2]
    transform(input_csv, output_dir)

if __name__ == "__main__":
    main()