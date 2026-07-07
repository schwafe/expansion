#!/usr/bin/env python3
"""
Clean the Wortstamm/Deklination columns of data/simple.csv and data/complex.csv
into a strict, machine-parseable format (so that full paradigms can be
generated from them, e.g. for validating the inflected expansions).

Canonical format
================

Wortstamm: one part per word of the Auflösung, parts separated by "; ".
  - declinable noun/adjective:  `stem -ending`
      * the ending is the genitive singular (genitive plural for words that
        only occur in the plural, marked `(Pl.)` in Deklination)
      * spelling variants of the stem: `stem1/stem2 -ending`
      * alternative endings: `stem -e/-i`
      * `ae` is written `e` (the paradigm generator must treat them as
        interchangeable, the RG uses both spellings)
  - verb: `present, perfect, supine` (three comma-separated stems,
      `-` for a missing stem, variants with `/`)
  - fixed word (not inflected, e.g. `et` or an attribute that is already
      in the genitive): the word itself, exactly as in the Auflösung
  - unknown/unclear: `?`
  - a trailing ` ?` marks the whole part as unverified

Deklination: one part per Wortstamm part, separated by "; ".
  - nouns: `a`, `o`, `u`, `e`, `i`, `kons.`, `gem.`
      with optional markers `(m.)`, `(f.)`, `(n.)`, `(Pl.)`
      and `/`-separated alternatives when the declension is uncertain
  - adjectives (incl. participles): class plus `(Adj.)`, e.g. `o/a (Adj.)`,
      `i (Adj.)`
  - verbs: `a-Konj.`, `e-Konj.`, `i-Konj.`, `kons.-Konj.`, `gem.-Konj.`,
      `halbkons.-Konj.`, with optional `(Dep.)` for deponents
  - other: `Gerundium`, `Gerundivum`, `Adverb`
  - fixed word: `-`
  - unknown: `?`; a trailing ` ?` marks a part as unverified

Rows the script cannot confidently clean keep their original values and are
written to data/morphology_review.csv for manual attention.
"""

import re
import sys

import polars as pl

# --------------------------------------------------------------------------
# canonical grammar (used for validation)
# --------------------------------------------------------------------------

STEM = r"[A-Za-zäöü]+(?:/[A-Za-zäöü]+)*"
ENDING = r"-[a-z]+(?:/-[a-z]+)*"
NOUN_PART = re.compile(rf"^{STEM} {ENDING}( \?)?$")
VERB_STEM = rf"(?:{STEM}\??|-)"
VERB_PART = re.compile(rf"^{VERB_STEM}, {VERB_STEM}, {VERB_STEM}( \?)?$")

DEKL_CLASS = r"(?:a|o|u|e|i|kons\.|gem\.)"
DEKL_NOUN = re.compile(
    rf"^{DEKL_CLASS}(?:/{DEKL_CLASS})*"
    r"(?: \((?:m\.|f\.|n\.|Adj\.)\))*(?: \(Pl\.\))?(?: \?)?$"
)
DEKL_VERB = re.compile(
    r"^(?:a|e|i|kons\.|gem\.|halbkons\.)-Konj\.(?: \(Dep\.\))?(?: \?)?$"
)
DEKL_OTHER = {"Gerundium", "Gerundivum", "Adverb", "-", "?"}


def valid_wortstamm_part(part: str, aufloesung_words: list[str]) -> bool:
    if part == "?":
        return True
    if NOUN_PART.match(part) or VERB_PART.match(part):
        return True
    return part in aufloesung_words  # fixed word


def valid_deklination_part(part: str) -> bool:
    return bool(
        part in DEKL_OTHER or DEKL_NOUN.match(part) or DEKL_VERB.match(part)
    )


# --------------------------------------------------------------------------
# manual fixes, keyed by the original Wortstamm string
# (each entry: cleaned Wortstamm, cleaned Deklination or None to keep the
#  automatic cleaning of the Deklination column)
# --------------------------------------------------------------------------

MANUAL_BY_WORTSTAMM: dict[str, tuple[str, str | None]] = {
    # multi-word entries whose parts need aligning with the Auflösung words
    "abbat -is; convent -us": ("abbat -is; et; convent -us", "kons. (m.); -; u"),
    "commun -is serviti -i": ("commun -is; serviti -i", "i (Adj.) (n.); o (n.)"),
    "serviti -i commun -is": ("serviti -i; commun -is", "o (n.); i (Adj.) (n.)"),
    "curi -(a)e Roman -(a)e": ("curi -e; Roman -e", "a; o/a (Adj.)"),
    "Roman -(a)e curi -(a)e": ("Roman -e; curi -e", "o/a (Adj.); a"),
    "sed -is apostolic -(a)e": ("sed -is; apostolic -e", "kons. (f.); o/a (Adj.)"),
    "divin -orum offici -orum": (
        "divin -orum; offici -orum",
        "o/a (Adj.) (Pl.); o (n.) (Pl.)",
    ),
    "insigni -um pontificali -um": (
        "insigni -um; pontificali -um",
        "i (n.) (Pl.); i (Adj.) (Pl.)",
    ),
    "serviti -orum minut -orum": (
        "serviti -orum; minut -orum",
        "o (n.) (Pl.); o/a (Adj.) (Pl.)",
    ),
    "fruct -us, provent -us, reddit -us": (
        "fruct -us; provent -us; et; reddit -us",
        "u; u; -; u",
    ),
    # entries with prose notes about words that are not inflected
    "fratr -um; kalendarum wird nicht verändert": (
        "fratr -um; kalendarum",
        "kons. (Pl.); -",
    ),
    "marc -(a)e (argenti wird nicht verändert)": ("marc -e; argenti", "a; -"),
    # hospitale pauperum: the note gave no stem for hospitale
    "nur hospitale wird dekliniert": ("hospital -is; pauperum", "kons. (n.); -"),
    # stem variants of a single word listed as separate parts
    "acolit(h) -i; acolut -i": ("acolit/acolith/acolut -i", None),
    "baccalari -i; bacallari -i; baccalauri -i": (
        "baccalari/bacallari/baccalauri -i",
        None,
    ),
    # missing ending and typo (prothmartir -> prothomartir, cf. Auflösung)
    "prothmartir -": ("prothomartir -is", "kons."),
    # typo in the supine stem (compositum -> stem composit)
    "compon, composu, compost": ("compon, composu, composit", None),
    # deponents: no active perfect stem, the participle stem goes last
    "ingred, ingress": ("ingred, -, ingress", "halbkons.-Konj. (Dep.)"),
    "transgred, transgress": ("transgred, -, transgress", "halbkons.-Konj. (Dep.)"),
    # gratia expectativa: both words are declinable
    "expectativ -(a)e": ("grati -e; expectativ -e", "a; o/a (Adj.)"),
    # elemosina/elemosinaria: second variant has its own stem
    "elemosin -(a)e": ("elemosin/elemosinari -e", "a"),
    # plural-only neuters need (n.) to build the nominative in -a
    "limin -um (bereits Pl.)": ("limin -um", "kons. (n.) (Pl.)"),
    "mili -um (bereits Pl.)": ("mili -um", "i (n.) (Pl.)"),
    "insigni -um (bereits Pl.)": ("insigni -um", "i (n.) (Pl.)"),
    "pontifical -ium (bereits Pl.)": ("pontifical -ium", "i (Adj.) (Pl.)"),
    # beati: plural of the adjective
    "beat -orum/arum": ("beat -orum/-arum", "o/a (Adj.) (Pl.)"),
    # bare stems without endings
    "adiudic": ("adiudic, adiudicav, adiudicat", "a-Konj."),
    "coniugat": ("coniugat -i", "o/a (Adj.)"),
    "accept": ("accept -i", "o/a (Adj.)"),
    "confirmation": ("confirmation -is", "kons. (f.)"),
    "consanguine": ("consanguine -i", "o/a (Adj.)"),
}

# manual fixes keyed by (Auflösung, Wortstamm), for rows where the plain
# Wortstamm key is shared with other rows or where the alignment would wrongly
# treat a declinable word as fixed; both the raw and the once-cleaned
# Wortstamm are listed so the script stays reproducible and idempotent
MANUAL_BY_AUFLOESUNG: dict[tuple[str, str], tuple[str, str]] = {
    ("Romana curia", "curi -(a)e"): ("Roman -e; curi -e", "o/a (Adj.); a"),
    ("Romana curia", "Romana; curi -e"): ("Roman -e; curi -e", "o/a (Adj.); a"),
    ("sola signatura", "signatur -(a)e"): ("sol -e; signatur -e", "o/a (Adj.); a"),
    ("sola signatura", "sola; signatur -e"): ("sol -e; signatur -e", "o/a (Adj.); a"),
    ("altare portatile", "portatil -is"): ("altar -is; portatil -is", "i (n.); i (Adj.)"),
    ("altare portatile", "altare; portatil -is"): ("altar -is; portatil -is", "i (n.); i (Adj.)"),
    ("domus hospitalis", "hospital -is"): ("dom -us; hospital -is", "u (f.); i (Adj.)"),
    ("domus hospitalis", "domus; hospital -is"): ("dom -us; hospital -is", "u (f.); i (Adj.)"),
    # the comma in the Auflösung separates two alternative expansions,
    # so both words get their own morphology
    ("subdiaconatus, subdiaconia", "subdiaconat -us"): (
        "subdiaconat -us; subdiaconi -e",
        "u; a",
    ),
    ("subdiaconatus, subdiaconia", "subdiaconat -us; subdiaconia"): (
        "subdiaconat -us; subdiaconi -e",
        "u; a",
    ),
}

# manual fixes for the Deklination column alone, keyed by original value
MANUAL_DEKLINATION: dict[str, str] = {
    "o (Adj.) aber unregelmäßig: Gen. alius, Dat. alii": "o/a (Adj.)",
    "o (Adj.; n. Pl.) o (n. Pl.)": "o/a (Adj.) (Pl.); o (n.) (Pl.)",
    "o (n.) und konsonantisch (n.)": "o (n.); kons. (n.)",
    "konsonantisch und a": "kons. (f.); o/a (Adj.)",
    "konsonantisch/u": "kons. (m.); -; u",
    "beide a": "a; o/a (Adj.)",  # only used for 'Romana curia'
    "beide o (n.)": "o (n.) (Pl.); o/a (Adj.) (Pl.)",
    "beide i (n.)": "i (n.) (Pl.); i (Adj.) (Pl.)",
    "alle u": "u; u; -; u",
}

# notes that are moved from Deklination into Anmerkungen
DEKLINATION_NOTES: dict[str, str] = {
    "o (Adj.) aber unregelmäßig: Gen. alius, Dat. alii": "unregelmäßig: Gen. alius, Dat. alii",
}

DEKLINATION_MAP: dict[str, str] = {
    "konsonantisch": "kons.",
    "konsonantisch (m.)": "kons. (m.)",
    "konsonantisch (f.)": "kons. (f.)",
    "konsonantisch (n.)": "kons. (n.)",
    "konsonantisch (Adj.)": "kons. (Adj.)",
    "konsonantisch ?": "kons. ?",
    "konsonantisch/gemischt?": "kons./gem. ?",
    "i/konsonantisch ?": "i/kons. ?",
    "i/konsonantisch ? (Adj.)": "i/kons. (Adj.) ?",
    "gemischt": "gem.",
    "konsonantische Konj.": "kons.-Konj.",
    "gemischte Konj.": "gem.-Konj.",
    "halbkonsonantische Konj.": "halbkons.-Konj.",
    "A-Konj.": "a-Konj.",
    "a (m.!)": "a (m.)",
    # adjectives in -us/-a/-um: unify to o/a (Adj.)
    "o (Adj.)": "o/a (Adj.)",
    "a (Adj.)": "o/a (Adj.)",
    "o/a (Adj.)": "o/a (Adj.)",
    "o (auch Adj.)": "o/a (Adj.)",
    "o/a": "o/a (Adj.)",  # only used for solutus/soluta
    "i-Dekl. (Adj.)": "i (Adj.)",
    "i-Dekl. (Adj.) (n.)": "i (Adj.)",
    "i (Adj.) ?": "i (Adj.) ?",
    "o (Gerundivum)": "Gerundivum",
}


# --------------------------------------------------------------------------
# automatic cleaning
# --------------------------------------------------------------------------


def aufloesung_words(aufloesung: str | None) -> list[str]:
    """Words of the Auflösung, without punctuation and German note-parentheses."""
    if aufloesung is None:
        return []
    text = aufloesung.strip().rstrip(";").strip()
    text = re.sub(r"\([^)]*:[^)]*\)", "", text)  # notes like '(ohne Zusatz: ...)'
    text = text.replace("(", " ").replace(")", " ")
    return [w for w in re.split(r"[,\s]+", text) if w and w != "?"]


def expand_stem_variants(stem: str) -> str:
    """Expand bracket notations into explicit /-separated variants."""
    variants = [""]
    pos = 0
    for m in re.finditer(r"\[([a-z](?:/?[a-z])*)\]|\(([a-z]+)\)", stem):
        fixed = stem[pos : m.start()]
        variants = [v + fixed for v in variants]
        if m.group(1) is not None:  # [i/e] or [iy]: one of the letters
            options = [c for c in m.group(1) if c != "/"]
        else:  # (h): optional letters
            options = ["", m.group(2)]
        variants = [v + o for v in variants for o in options]
        pos = m.end()
    variants = [v + stem[pos:] for v in variants]
    return "/".join(dict.fromkeys(variants))


def clean_noun_part(part: str) -> str | None:
    """Normalize one 'stem -ending' part; None if it doesn't look like one."""
    part = part.strip()
    if NOUN_PART.match(part):  # already canonical
        return part
    unsure = part.endswith("?")
    part = part.rstrip("?").strip()

    # 'stem1 -e1/stem2 -e2' -> merge if the endings agree
    subparts = re.split(r"/(?=[A-Za-zäöü]+ -)", part)
    stems, endings = [], []
    for sub in subparts:
        # tolerate misplaced hyphens: 'archidiacon-i', 'abolition- is'
        m = re.match(r"^([A-Za-zäöü()\[\]/]+)\s*-\s*([a-zäöü()/?-]+)$", sub.strip())
        if not m:
            return None
        stems.append(expand_stem_variants(m.group(1)))
        ending = m.group(2).rstrip("?").strip()
        ending = ending.replace("(a)e", "e")
        endings.append("/".join("-" + e.lstrip("-") for e in ending.split("/-")))
    if len(set(endings)) != 1:
        return None
    stem = "/".join(dict.fromkeys(s for group in stems for s in group.split("/")))
    result = f"{stem} {endings[0]}"
    if unsure:
        result += " ?"
    return result if NOUN_PART.match(result) else None


def clean_verb_part(part: str) -> str | None:
    """Normalize a 'present, perfect, supine' stem list; None if not a verb."""
    stems = [s.strip() for s in part.split(",")]
    if not 2 <= len(stems) <= 3:
        return None
    cleaned = []
    for stem in stems:
        stem = re.sub(r"^(\S+) \((\S+)\)$", r"\1/\2", stem)  # 'collat (conlat)'
        if stem == "-" or re.match(rf"^{STEM}\??$", stem):
            cleaned.append(stem)
        else:
            return None
    while len(cleaned) < 3:
        cleaned.append("-")
    result = ", ".join(cleaned)
    return result if VERB_PART.match(result) else None


def align_with_aufloesung(parts: list[str], words: list[str]) -> list[str] | None:
    """
    Insert the non-inflected Auflösung words verbatim between the cleaned
    parts so that there is exactly one part per word. Parts are matched to
    words by common prefix. Returns None if the parts cannot be aligned.
    """

    def matches(part: str, word: str) -> bool:
        stem = part.split(" ")[0].split("/")[0].rstrip("?")
        common = 0
        for a, b in zip(stem.lower(), word.lower()):
            if a != b:
                break
            common += 1
        return common >= min(3, len(stem), len(word))

    aligned = []
    w = 0
    for part in parts:
        while w < len(words) and not matches(part, words[w]):
            aligned.append(words[w])  # fixed word
            w += 1
        if w >= len(words):
            return None
        aligned.append(part)
        w += 1
    aligned.extend(words[w:])
    return aligned


def clean_wortstamm(wortstamm: str, aufloesung: str | None) -> tuple[str | None, str | None]:
    """
    Returns (cleaned value, plural_marker) where plural_marker is '(Pl.)' if
    the entry was marked as plural-only. Cleaned value is None if the entry
    could not be cleaned automatically.
    """
    ws = re.sub(r"\s+", " ", wortstamm).strip()

    plural = None
    if re.search(r"\(bereits (Pl\.|Plural)\)", ws):
        plural = "(Pl.)"
        ws = re.sub(r"\s*\(bereits (Pl\.|Plural)\)", "", ws).strip()

    if ws == "?":
        return "?", plural

    words = aufloesung_words(aufloesung)

    # verb? (single part, comma-separated stems without '-endings')
    verb = clean_verb_part(ws)
    if verb is not None:
        return verb, plural

    # noun parts: split on ';', or on commas/spaces between 'stem -ending' pairs
    raw_parts = [p.strip() for p in ws.split(";") if p.strip()]
    if len(raw_parts) == 1:
        pairs = re.findall(r"[A-Za-zäöü()\[\]/]+\s+-[a-zäöü()/?-]+\s*\??", ws)
        if len(pairs) > 1 and "".join(pairs).replace(" ", "") == ws.replace(
            ",", ""
        ).replace(" ", ""):
            raw_parts = [p.strip() for p in pairs]

    cleaned_parts = []
    for part in raw_parts:
        if part in words or part == "?":  # fixed word or unknown (already clean)
            cleaned_parts.append(part)
            continue
        cleaned = clean_noun_part(part)
        if cleaned is None:
            # bare stem: append the ending of the Auflösung word if obvious?
            # no -- too risky, leave for manual review
            return None, plural
        cleaned_parts.append(cleaned)

    if len(words) > len(cleaned_parts):
        aligned = align_with_aufloesung(cleaned_parts, words)
        if aligned is None:
            return None, plural
        cleaned_parts = aligned
    elif words and len(words) < len(cleaned_parts):
        return None, plural  # more stems than words -> needs manual review

    return "; ".join(cleaned_parts), plural


def clean_deklination(
    deklination: str, n_parts: int, plural: str | None
) -> str | None:
    """Canonicalize the Deklination column; None if it needs manual review."""
    dk = re.sub(r"\s+", " ", deklination).strip()

    if dk in MANUAL_DEKLINATION:
        dk = MANUAL_DEKLINATION[dk]
    else:
        dk = "; ".join(
            DEKLINATION_MAP.get(p.strip(), p.strip()) for p in dk.split(";")
        )

    parts = [p.strip() for p in dk.split(";")]
    if plural:
        parts = [
            p if p.endswith("(Pl.)") or p in DEKL_OTHER else f"{p} {plural}"
            for p in parts
        ]
    dk = "; ".join(parts)

    if not all(valid_deklination_part(p) for p in parts):
        return None
    return dk


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def clean_file(path: str) -> tuple[pl.DataFrame, list[dict]]:
    df = pl.read_csv(path)
    review = []
    new_ws_col, new_dk_col, new_an_col = [], [], []

    for row in df.iter_rows(named=True):
        ws, dk, an = row["Wortstamm"], row["Deklination"], row["Anmerkungen"]
        aufloesung = row["Auflösung"]

        # move prose notes out of Deklination
        if dk is not None and dk.strip() in DEKLINATION_NOTES:
            note = DEKLINATION_NOTES[dk.strip()]
            an = f"{an}; {note}" if an else note

        new_ws, new_dk, plural = ws, dk, None
        issue = None

        if ws is not None:
            key = re.sub(r"\s+", " ", ws).strip()
            aufl_key = (
                re.sub(r"\s+", " ", aufloesung).strip() if aufloesung else ""
            )
            if (aufl_key, key) in MANUAL_BY_AUFLOESUNG:
                new_ws, new_dk = MANUAL_BY_AUFLOESUNG[(aufl_key, key)]
                new_ws_col.append(new_ws)
                new_dk_col.append(new_dk)
                new_an_col.append(an)
                continue
            if key in MANUAL_BY_WORTSTAMM:
                new_ws, manual_dk = MANUAL_BY_WORTSTAMM[key]
                # the same Wortstamm can be shared by rows whose Auflösung has
                # extra fixed words (e.g. 'limina' vs 'limina apostolorum')
                words = aufloesung_words(aufloesung)
                parts = [p.strip() for p in new_ws.split(";")]
                if len(words) > len(parts):
                    aligned = align_with_aufloesung(parts, words)
                    if aligned is not None:
                        if manual_dk is not None:
                            dk_iter = iter(
                                p.strip() for p in manual_dk.split(";")
                            )
                            manual_dk = "; ".join(
                                next(dk_iter) if p in parts else "-"
                                for p in aligned
                            )
                        new_ws = "; ".join(aligned)
                if manual_dk is not None:
                    new_dk = manual_dk
                    new_ws_col.append(new_ws)
                    new_dk_col.append(new_dk)
                    new_an_col.append(an)
                    continue
            else:
                new_ws, plural = clean_wortstamm(ws, aufloesung)
                if new_ws is None:
                    issue = "Wortstamm not automatically cleanable"
                    new_ws = ws

        if new_dk is not None and issue is None:
            n_parts = len(new_ws.split(";")) if new_ws else 1
            cleaned_dk = clean_deklination(new_dk, n_parts, plural)
            if cleaned_dk is None:
                issue = "Deklination not automatically cleanable"
            else:
                new_dk = cleaned_dk

        # pad the Deklination with '-' for fixed (non-declined) words
        if new_dk is not None and new_ws is not None and issue is None:
            ws_parts = [p.strip() for p in new_ws.split(";")]
            dk_parts = [p.strip() for p in new_dk.split(";")]
            if len(dk_parts) < len(ws_parts):
                declinable = [(" -" in p) or ("," in p) for p in ws_parts]
                if sum(declinable) == len(dk_parts):
                    dk_iter = iter(dk_parts)
                    new_dk = "; ".join(
                        next(dk_iter) if d else "-" for d in declinable
                    )

        # final validation of the pair
        if issue is None and new_ws is not None:
            words = aufloesung_words(aufloesung)
            ws_parts = [p.strip() for p in new_ws.split(";")]
            if not all(valid_wortstamm_part(p, words) for p in ws_parts):
                issue = "cleaned Wortstamm does not match the format"
            elif new_dk is not None:
                dk_parts = [p.strip() for p in new_dk.split(";")]
                if len(dk_parts) != len(ws_parts) and len(dk_parts) != 1:
                    issue = "Wortstamm and Deklination have different numbers of parts"

        if issue is not None:
            review.append(
                {
                    "file": path,
                    "Abkürzung": row["Abkürzung"],
                    "Auflösung": aufloesung,
                    "Wortstamm": ws,
                    "Deklination": dk,
                    "issue": issue,
                }
            )
            new_ws, new_dk = ws, dk  # keep the original values

        new_ws_col.append(new_ws)
        new_dk_col.append(new_dk)
        new_an_col.append(an)

    df = df.with_columns(
        pl.Series("Wortstamm", new_ws_col, dtype=pl.String),
        pl.Series("Deklination", new_dk_col, dtype=pl.String),
        pl.Series("Anmerkungen", new_an_col, dtype=pl.String),
    )
    return df, review


def main():
    write = "--write" in sys.argv
    all_review = []

    for path in ("data/simple.csv", "data/complex.csv"):
        df, review = clean_file(path)
        all_review.extend(review)

        changed_ws = df.get_column("Wortstamm")
        original = pl.read_csv(path)
        n_ws = (
            (changed_ws != original.get_column("Wortstamm"))
            .fill_null(False)
            .sum()
        )
        n_dk = (
            (df.get_column("Deklination") != original.get_column("Deklination"))
            .fill_null(False)
            .sum()
        )
        print(f"{path}: {n_ws} Wortstamm and {n_dk} Deklination values cleaned, "
              f"{len(review)} rows for manual review")

        if write:
            df.write_csv(path)

    if all_review:
        review_df = pl.DataFrame(all_review)
        if write:
            review_df.write_csv("data/morphology_review.csv")
        print("\nrows for manual review:")
        for r in all_review:
            print(f"  [{r['file']}] {r['Abkürzung']!r} | Aufl={r['Auflösung']!r}")
            print(f"      WS={r['Wortstamm']!r} | Dekl={r['Deklination']!r} | {r['issue']}")

    if not write:
        print("\ndry run -- pass --write to update the CSV files")


if __name__ == "__main__":
    main()
