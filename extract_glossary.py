#!/usr/bin/env python3
"""
Step 0: extract the abbreviation glossary into data/simple.csv and
data/complex.csv.

Source of truth is data/RGAbkVerz.csv (the raw export of the RG
Abkürzungsverzeichnis) -- it is never hand-edited. Every manual decision
lives in this script as an explicit, documented correction, so the whole
extraction is reproducible: `python extract_glossary.py --write` rebuilds
the outputs from scratch.

Stages (each stage is a function of the same name):

 1. load          read the CSV, deduplicate the double "Bemerkungen" header
                  to Bemerkungen_1/_2, strip surrounding whitespace.
 2. corrections   apply the CORRECTIONS/ADDITIONS tables (typo fixes, row
                  splits/deletions, extra abbreviations). A correction that
                  no longer matches fails the run, so the tables stay in
                  sync if the glossary export is ever updated.
 3. inherit       continuation rows (blank Abkürzung) inherit the
                  abbreviation from the row above.
 4. normalize     - collapse runs of spaces in Abkürzung/Auflösung/RG1-9
                  - drop rows whose Auflösung is empty or "?" (unusable)
                  - a trailing ";" on the Auflösung marks an abbreviation
                    with several meanings -> remembered as a flag (forces
                    the complex split), then stripped
                  - an internal ";" separates alternative expansions ->
                    the row is split into one row per alternative
                  - a trailing " ?" (unverified expansion) and a
                    "(dekliniert)" marker (which also forces the complex
                    split) move into the Anmerkungen
                  - a free-standing parenthesized part is kept as part of
                    the expansion if the abbreviation has more parts than
                    the words outside it ('def. nat. s. c.'), otherwise
                    it is one of the glossary's notes and moves into the
                    Anmerkungen ('natalis (def.)', 'sancti (Plural)').
                    A parenthesis attached to a word ('op(p)idum') is
                    variant notation, not a note -> left to stage 6
 5. rg_columns    the RG1-9 cells list how volume n abbreviates the entry;
                  each cell is reduced to the row's own abbreviation (or
                  emptied). A cell naming a *different* abbreviation (with
                  a period) spawns a derived row for it; a written-out form
                  (no period) cannot be reduced and later forces the
                  complex split. Derived rows for a capitalized
                  abbreviation get their Auflösung capitalized (names).
 6. resolve       variant notation in the Auflösung is resolved against
                  the row's own abbreviation:
                  - spelling variants inside a word, `op(p)idum` or
                    `mart[iy]r`: the variant sharing the longest prefix
                    with the abbreviation wins ('renen.' -> 'renensis');
                    if the abbreviation fits several of them ('op.' fits
                    'opidum' and 'oppidum'), the spelling the RG uses
                    more often wins
                  - `/` between phrases (a side contains a space) or
                    between full words: alternative expansions; if the
                    abbreviation's letters single out one, it wins,
                    otherwise the row is split into one row per
                    alternative (they end up as step-2 candidates)
                  (suffix notation like `statuta/um` is not resolved
                  mechanically -- those few rows are handled by explicit
                  corrections)
 7. merge         rows with the same (Abkürzung, Auflösung) -- e.g. an
                  alias entry plus a row derived from an RG column -- are
                  merged: RG cells are united, first non-empty value wins
                  elsewhere.
 8. corpus        every abbreviation is searched in the RG corpus
                  (periods optional -- they are sometimes missing in the
                  text). Abbreviations that never occur are dropped (and
                  reported); the matching volumes go into the `volumes`
                  column. Rows from ADDITIONS are kept regardless.
 9. split         an abbreviation is *complex* -- all of its rows go to
                  complex.csv -- if any of its rows has several meanings
                  (";" flag), an RG cell that could not be reduced, or was
                  forced by a correction; likewise if it has several
                  meanings and one claims no volume at all (the others'
                  claims then cannot be trusted to be exclusive).
                  Everything else is simple: step 1 can replace it by
                  plain rules, expanding each volume only when exactly
                  one row claims it.
10. clean_complex moving the notes out of the Auflösung can make two
                  complex entries identical, so they are merged again
                  (they are the candidate list of step 2).
11. morphology    clean the Wortstamm/Deklination columns into the strict
                  format of paradigm.py (clean_morphology.py does the
                  work; rows it cannot clean keep their values and are
                  reported).
12. validate      quality checks against the corpus, written to
                  data/review/ (see the report for the file list).
13. report        data/review/extraction_report.md documents every count,
                  correction and flagged row of the run.

--diff-old additionally compares the produced tables with the simple.csv/
complex.csv currently on disk and writes the row-level differences to
data/review/, so a re-extraction can be reviewed before --write.
"""

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

import polars as pl

import clean_morphology
from clean_morphology import aufloesung_words

GLOSSARY = "data/RGAbkVerz.csv"
CORPUS = "data/RG_header_sublemma_all.csv"
SIMPLE_OUT = "data/simple.csv"
COMPLEX_OUT = "data/complex.csv"
REVIEW_DIR = Path("data/review")

RG_COLUMNS = [f"RG{i}" for i in range(1, 10)]
COLUMNS = [
    "Abkürzung", "Auflösung", "Übersetzung", "Anmerkungen",
    "Wortstamm", "Deklination", *RG_COLUMNS, "Bemerkungen_1", "Bemerkungen_2",
]
# internal row keys (not written to the outputs)
MULTI = "_multi"            # Auflösung carried a ";": several meanings
RG_MISMATCH = "_rg_mismatch"  # an RG cell could not be reduced
FORCED = "_force_complex"   # forced complex by a correction
ADDED = "_added"            # row comes from ADDITIONS (kept in step 7)


# ---------------------------------------------------------------------------
# stage 2: corrections
# ---------------------------------------------------------------------------


@dataclass
class Correction:
    """One documented manual intervention on the raw glossary rows."""

    reason: str
    match: dict[str, str]                 # column -> exact cell value
    set: dict[str, str] | None = None     # replace these cells
    delete: bool = False                  # remove the matched row
    add: list[dict] | None = None         # insert these rows after it
    force_complex: bool = False           # send the abbreviation to complex.csv
    count: int = 1                        # expected number of matched rows


# The first block ports the pre-2025-07 hand edits that turned the raw
# export into the old working copy (data/abbreviations.csv); they were
# recovered from the diff of the two files. The reasons follow the
# Bemerkungen/Anmerkungen of the glossary itself where it gives one.
CORRECTIONS: list[Correction] = [
    Correction(
        reason="volume reference in an RG cell belongs into the Bemerkungen",
        match={"Auflösung": "?", "RG2": "a. (Bd. II 25)"},
        set={"RG2": "a.", "Bemerkungen_2": "(Bd. II 25)"},
    ),
    Correction(
        reason="counting note '1x' is not part of the abbreviation",
        match={"Abkürzung": "abb.", "RG4": "abb.; 1x abbas"},
        set={"RG4": "abb.; abbas"},
    ),
    Correction(
        reason="the currency qualifier is a note, not part of the expansion",
        match={"Abkürzung": "adc."},
        set={"Auflösung": "auri de camera", "Bemerkungen_2": "(fl. vel duc.)"},
    ),
    Correction(
        reason="'add. (ment.)' bundles two abbreviations; the RG cells show "
        "both are used",
        match={"Abkürzung": "add. (ment.)"},
        set={"Abkürzung": "add.", "Auflösung": "addendo",
             "RG2": "add.", "RG4": "add."},
        add=[{"Abkürzung": "add. ment.", "Auflösung": "addendo mentionem",
              "Deklination": "Gerundium", "RG2": "add. ment.",
              "RG4": "add. ment."}],
    ),
    Correction(
        reason="'ann. ?' marks an unverified guess (see Anmerkungen of the "
        "row: ann. stands for annata in Bd. 4/5), drop the guess",
        match={"Abkürzung": "ann.", "RG4": "annuus; ann. ?"},
        set={"RG4": "annuus", "RG5": "annuus"},
    ),
    Correction(
        reason="unidentified abbreviation (Auflösung '?'), unusable",
        match={"Abkürzung": "Arm."},
        delete=True,
    ),
    Correction(
        reason="unidentified abbreviation (Auflösung '?'), unusable",
        match={"Abkürzung": "cont."},
        delete=True,
    ),
    Correction(
        reason="no Auflösung given, unusable",
        match={"Abkürzung": "cruc."},
        delete=True,
    ),
    Correction(
        reason="missing closing parenthesis",
        match={"Abkürzung": "def. nat. (s. c.)"},
        set={"Auflösung": "defectus natalium (de soluto et coniugata genitus)"},
    ),
    Correction(
        reason="which abbreviation 'e.' stands for cannot be determined "
        "(see its Bemerkungen); the specific combinations have their own "
        "entries (e. m., e. t., s. e. d., s. e. p.)",
        match={"Abkürzung": "e.", "Auflösung": "extra (in e. m. sowie e. t.)"},
        delete=True,
    ),
    Correction(
        reason="continuation row of the deleted 'e.' entry",
        match={"Abkürzung": "", "Auflösung": "expectatio (in s. e. p.)"},
        delete=True,
    ),
    Correction(
        reason="continuation row of the deleted 'e.' entry",
        match={"Abkürzung": "", "Auflösung": "eodem (in s. e. d.)"},
        delete=True,
    ),
    Correction(
        reason="missing period after the RG1 variant",
        match={"Abkürzung": "facult.", "RG1": "fac.; facult"},
        set={"RG1": "fac.; facult."},
    ),
    Correction(
        reason="the abbreviation 'hosp. pauper.' does not occur; the RG "
        "cells show 'hosp. pauperum' (partly written out) is what is used",
        match={"Abkürzung": "hosp. pauper."},
        set={"Abkürzung": "hosp. pauperum"},
    ),
    Correction(
        reason="glossary marks 'in cur. defunct.' as inexistent: the phrase "
        "is written out (or only cur. is abbreviated) in the volumes",
        match={"Abkürzung": "in cur. defunct."},
        set={"Anmerkungen": ""},
        add=[{"Abkürzung": "in cur. defunctus",
              "Auflösung": "in curia defunctus",
              "Übersetzung": "am päpstlichen Hof gestorben",
              "Wortstamm": "defunct -i", "Deklination": "o (Adj.)"}],
    ),
    Correction(
        reason="'(usw.)' is a note: iur. stands for any inflected form, the "
        "genitive is just the most frequent",
        match={"Abkürzung": "iur."},
        set={"Auflösung": "iuris"},
    ),
    Correction(
        reason="glossary marks 'k.' as inexistent",
        match={"Abkürzung": "k."},
        delete=True,
    ),
    Correction(
        reason="'lim. (appl.)' bundles 'lim.' and 'lim. appl.'",
        match={"Abkürzung": "lim."},
        set={"Auflösung": "limina", "Übersetzung": "Schwellen"},
        add=[{"Abkürzung": "lim. appl.", "Auflösung": "limina apostolorum",
              "Übersetzung": "Schwellen der Gräber der Apostel Petrus und "
              "Paulus; (Pflicht der Bischöfe zum regelmäßigen Besuch der "
              "Kurie);",
              "Wortstamm": "limin -um (bereits Pl.)",
              "Deklination": "konsonantisch"}],
    ),
    Correction(
        reason="'limin. (appl.)' bundles 'limin.' and 'limin. appl.'",
        match={"Abkürzung": "limin."},
        set={"Auflösung": "limina", "Übersetzung": "Schwellen"},
        add=[{"Abkürzung": "limin. appl.", "Auflösung": "limina apostolorum",
              "Wortstamm": "limin -um (bereits Pl.)",
              "Deklination": "konsonantisch"}],
    ),
    Correction(
        reason="duplicated value in the RG3 cell",
        match={"Abkürzung": "lite pend."},
        set={"RG3": "lit. pend."},
    ),
    Correction(
        reason="per its Bemerkungen, 'n.' has a different, unknown meaning "
        "in Bd. 1",
        match={"Abkürzung": "n.", "Auflösung": "non"},
        set={"RG1": ""},
    ),
    Correction(
        reason="the 'retin.' RG cells slipped into the preceding "
        "'restitutio' continuation row",
        match={"Abkürzung": "", "Auflösung": "restitutio",
               "RG2": "retin."},
        set={"RG2": "", "RG3": "", "RG4": "", "RG5": "", "RG6": "",
             "RG7": "", "RG8": "", "RG9": ""},
    ),
    Correction(
        reason="the 'retin.' RG cells slipped into the preceding row "
        "(see above)",
        match={"Abkürzung": "retin.", "RG2": ""},
        set={"RG2": "retin.", "RG3": "retin.", "RG4": "retin.",
             "RG5": "retin.", "RG6": "retin.", "RG7": "retin.",
             "RG8": "retin.", "RG9": "retin."},
    ),
    Correction(
        reason="'communi(s) serv.' bundles two spellings used in the volumes",
        match={"Abkürzung": "serv. commun."},
        set={"RG7": "communi serv.; communis serv.",
             "RG9": "serv. commun.; commun. serv.; communi serv.; "
                    "communis serv."},
    ),
    Correction(
        reason="stray space inside the RG4 cell",
        match={"Abkürzung": "vac.", "RG4": "vac ."},
        set={"RG4": "vac."},
    ),
    Correction(
        reason="stray space inside the RG7 cell",
        match={"Abkürzung": "n. o.", "RG7": "n. o ."},
        set={"RG7": "n. o."},
    ),
    # ----- alternative expansions the notation of which cannot be split
    # mechanically (a comma that elsewhere separates enumerations, or
    # suffix notation like 'statuta/um'); each alternative becomes its own
    # row with its own morphology
    Correction(
        reason="comma separates two alternative expansions",
        match={"Abkürzung": "expect."},
        set={"Auflösung": "expectatio"},
        add=[{"Abkürzung": "expect.", "Auflösung": "gratia expectativa",
              "Übersetzung": "Anwartschaft (auf ein noch nicht freies "
              "Kirchenamt), Exspektanz",
              "Wortstamm": "grati -e; expectativ -e",
              "Deklination": "a; o/a (Adj.)"}],
    ),
    Correction(
        reason="comma separates two alternative expansions",
        match={"Abkürzung": "profes."},
        set={"Auflösung": "professa", "Wortstamm": "profess -e",
             "Deklination": "o/a (Adj.)"},
        add=[{"Abkürzung": "profes.", "Auflösung": "professus",
              "Wortstamm": "profess -i", "Deklination": "o/a (Adj.)"}],
    ),
    Correction(
        reason="comma separates two alternative expansions",
        match={"Abkürzung": "spect."},
        set={"Auflösung": "spectare"},
        add=[{"Abkürzung": "spect.", "Auflösung": "spectans",
              "Wortstamm": "spectant -is", "Deklination": "gem."}],
    ),
    Correction(
        reason="comma separates two alternative expansions",
        match={"Abkürzung": "subdiacon."},
        set={"Auflösung": "subdiaconatus"},
        add=[{"Abkürzung": "subdiacon.", "Auflösung": "subdiaconia",
              "Übersetzung": "Weihegrad; Amt des Subdiakons",
              "Wortstamm": "subdiaconi -e", "Deklination": "a"}],
    ),
    Correction(
        reason="suffix notation 'statuta/um' written out",
        match={"Abkürzung": "statut."},
        set={"Auflösung": "statuta", "Wortstamm": "statut -e",
             "Deklination": "a"},
        add=[{"Abkürzung": "statut.", "Auflösung": "statutum",
              "Wortstamm": "statut -i", "Deklination": "o (n.)"}],
    ),
    Correction(
        reason="suffix notation 'caritatis/ivum' written out",
        match={"Abkürzung": "subsid. car."},
        set={"Auflösung": "subsidium caritatis"},
        add=[{"Abkürzung": "subsid. car.",
              "Auflösung": "subsidium caritativum"}],
    ),
    Correction(
        reason="suffix notation 'caritatis/ivum' written out",
        match={"Abkürzung": "subsid. carit."},
        set={"Auflösung": "subsidium caritatis"},
        add=[{"Abkürzung": "subsid. carit.",
              "Auflösung": "subsidium caritativum"}],
    ),
    Correction(
        reason="suffix notation 'dato/a' written out",
        match={"Abkürzung": "", "Auflösung": "sine dato/a;"},
        set={"Auflösung": "sine dato;"},
        add=[{"Auflösung": "sine data;"}],
    ),
    Correction(
        reason="suffix notation 'dato/data' written out",
        match={"Abkürzung": "d. d."},
        set={"Auflösung": "de dato"},
        add=[{"Abkürzung": "d. d.", "Auflösung": "de data"}],
    ),
    Correction(
        reason="suffix notation 'solutus/soluta' written out; the German "
        "usage note moves into the Anmerkungen",
        match={"Abkürzung": "", "Auflösung": "(nur bei def. nat.:) solutus/soluta"},
        set={"Auflösung": "solutus", "Anmerkungen": "nur bei def. nat.",
             "Wortstamm": "solut -i", "Deklination": "o/a (Adj.)"},
        add=[{"Auflösung": "soluta", "Übersetzung": "ledig",
              "Anmerkungen": "nur bei def. nat.",
              "Wortstamm": "solut -e", "Deklination": "o/a (Adj.)"}],
    ),
    Correction(
        reason="the German grammar note is not part of the expansion",
        match={"Abkürzung": "n. o."},
        set={"Auflösung": "non obstante/obstantibus",
             "Anmerkungen": "als Ablativus absolutus"},
    ),
    Correction(
        reason="the German grammar note is not part of the expansion",
        match={"Abkürzung": "non obst."},
        set={"Auflösung": "non obstante/obstantibus",
             "Anmerkungen": "als Ablativus absolutus"},
    ),
    Correction(
        reason="the German grammar note is not part of the expansion",
        match={"Abkürzung": "non obstant."},
        set={"Auflösung": "non obstante/obstantibus",
             "Anmerkungen": "als Ablativus absolutus"},
    ),
    Correction(
        reason="'curia' without an addition refers to the Romana curia "
        "(the glossary's own note), which is what the RG writes out",
        match={"Abkürzung": "cur."},
        set={"Auflösung": "Romana curia",
             "Anmerkungen": "cur. ohne Zusatz steht für die Romana curia"},
    ),
    Correction(
        reason="'identisch' is a German editorial gloss, not a Latin "
        "expansion -- do not let step 1 insert it into the texts",
        match={"Abkürzung": "id."},
        force_complex=True,
    ),
    Correction(
        reason="the glossary leaves 'cur.' abbreviated inside the "
        "expansion; an expansion must not contain an abbreviation",
        match={"Abkürzung": "o. in cur.", "Auflösung": "obitus in cur."},
        set={"Auflösung": "obitus in curia"},
    ),
]

# Rows that are not in the glossary at all. The matrimony entries were
# suggested by OpenAI GPT-5.5 from the texts; the others were found while
# expanding (they are combinations whose parts are in the glossary).
# These rows skip the corpus-existence filter (stage 7).
ADDITIONS: list[tuple[str, dict]] = [
    ("found in the texts, suggested by OpenAI GPT-5.5",
     {"Abkürzung": "conf. disp. sup. matrim.",
      "Auflösung": "confirmatio dispensationis super matrimonio"}),
    ("found in the texts, suggested by OpenAI GPT-5.5",
     {"Abkürzung": "de disp. sup. matrim.",
      "Auflösung": "de dispensatione super matrimonio"}),
    ("found in the texts, suggested by OpenAI GPT-5.5",
     {"Abkürzung": "de conf. disp. sup. matrim.",
      "Auflösung": "confirmatione dispensationis super matrimonio"}),
    ("found in the texts, suggested by OpenAI GPT-5.5",
     {"Abkürzung": "de ref. disp. sup. matrim.",
      "Auflösung": "de reformatione dispensationis super matrimonio"}),
    ("combination of glossary entries, frequent in the texts",
     {"Abkürzung": "cler. Magunt. dioc.",
      "Auflösung": "clericus Maguntinae diocesis"}),
    ("combination of glossary entries, frequent in the texts",
     {"Abkürzung": "Colon. dioc.", "Auflösung": "Coloniensis diocesis"}),
    ("combination of glossary entries, frequent in the texts",
     {"Abkürzung": "eccl. Magunt.", "Auflösung": "ecclesia Maguntina"}),
    ("combination of glossary entries, frequent in the texts",
     {"Abkürzung": "eccl. s.", "Auflösung": "ecclesia sancti"}),
    ("combination of glossary entries, frequent in the texts",
     {"Abkürzung": "Magunt. dioc.", "Auflösung": "Maguntinae diocesis"}),
    ("combination of glossary entries, frequent in the texts",
     {"Abkürzung": "par. eccl.", "Auflösung": "parochialis ecclesia"}),
    ("combination of glossary entries, frequent in the texts",
     {"Abkürzung": "vac. p. o.", "Auflösung": "vacante per obitum"}),
    ("combination of glossary entries, frequent in the texts",
     {"Abkürzung": "vac. p. res.", "Auflösung": "vacante per resignationem"}),
    ("combination of glossary entries, frequent in the texts",
     {"Abkürzung": "vac. p. resign.",
      "Auflösung": "vacante per resignationem"}),
    ("not in the glossary, but 'off.' is used for officialis in Bd. 1 "
     "and possibly other volumes",
     {"Abkürzung": "off.", "Auflösung": "officialis",
      "Übersetzung": "Offizial", "Wortstamm": "official -is",
      "Deklination": "i ?"}),
    ("counterpart of 'sub eodem dat.' (the glossary lists only the "
     "masculine spelling among the RG variants)",
     {"Abkürzung": "sub eadem dat.", "Auflösung": "sub eadem data"}),
    ("partial expansion: only restit. is expanded, the following "
     "inflected form of bulla is kept as it is",
     {"Abkürzung": "restit. bulla", "Auflösung": "restitutio bulla"}),
    ("partial expansion: only restit. is expanded, the following "
     "inflected form of bulla is kept as it is",
     {"Abkürzung": "restit. bullam", "Auflösung": "restitutio bullam"}),
    ("partial expansion: only restit. is expanded, the following "
     "inflected form of bulla is kept as it is",
     {"Abkürzung": "restit. bullarum", "Auflösung": "restitutio bullarum"}),
    ("partial expansion: only restit. is expanded, the following "
     "inflected form of bulla is kept as it is",
     {"Abkürzung": "restit. bullas", "Auflösung": "restitutio bullas"}),
]


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------


def empty_row() -> dict:
    return {column: "" for column in COLUMNS}


def load(path: str = GLOSSARY) -> list[dict]:
    """Stage 1: read the raw glossary."""
    with open(path, encoding="utf-8-sig") as file:  # the export has a BOM
        reader = csv.reader(file)
        header = next(reader)
        assert header[:6] == COLUMNS[:6] and len(header) == len(COLUMNS), (
            f"unexpected glossary header: {header}"
        )
        rows = []
        for values in reader:
            row = {col: value.strip() for col, value in zip(COLUMNS, values)}
            rows.append(row)
    return rows


def apply_corrections(
    rows: list[dict],
    corrections: list[Correction] | None = None,
    additions: list[tuple[str, dict]] | None = None,
) -> tuple[list[dict], list[str]]:
    """Stage 2: apply CORRECTIONS and append ADDITIONS."""
    if corrections is None:
        corrections = CORRECTIONS
    if additions is None:
        additions = ADDITIONS
    log = []
    for correction in corrections:
        matched = [
            row for row in rows
            if all(row[col] == value for col, value in correction.match.items())
        ]
        if len(matched) != correction.count:
            raise SystemExit(
                f"correction {correction.match!r} matched {len(matched)} rows "
                f"instead of {correction.count} -- the glossary export "
                f"changed, update the CORRECTIONS table"
            )
        for row in matched:
            if correction.delete:
                rows.remove(row)
                log.append(f"deleted {row['Abkürzung']!r} / "
                           f"{row['Auflösung']!r}: {correction.reason}")
                continue
            if correction.set:
                row.update(correction.set)
            if correction.force_complex:
                row[FORCED] = True
            log.append(f"edited {row['Abkürzung']!r} / "
                       f"{row['Auflösung']!r}: {correction.reason}")
            if correction.add:
                position = rows.index(row) + 1
                for extra in correction.add:
                    rows.insert(position, empty_row() | extra)
                    position += 1
                    name = extra.get("Abkürzung") or extra["Auflösung"]
                    log.append(f"added {name!r}: {correction.reason}")
    for reason, extra in additions:
        rows.append(empty_row() | extra | {ADDED: True})
        log.append(f"added {extra['Abkürzung']!r}: {reason}")
    return rows, log


def inherit(rows: list[dict]) -> list[dict]:
    """Stage 3: continuation rows inherit the abbreviation from above."""
    current = ""
    for row in rows:
        if row["Abkürzung"]:
            current = row["Abkürzung"]
        else:
            row["Abkürzung"] = current
    return rows


# a parenthesized group that stands on its own (delimited by spaces or the
# ends of the string). One that is attached to a word -- 'op(p)idum',
# 'r(h)enensis', 'communi(s)' -- is spelling-variant notation, not a note,
# and belongs to the word: it is left alone here and resolved in stage 6.
FREE_PARENS = re.compile(r"(?<![A-Za-z])\([^()]*\)(?![A-Za-z])")


def resolve_parentheses(abbreviation: str, aufloesung: str) -> tuple[str, str]:
    """
    A free-standing parenthesized part of the Auflösung either belongs to
    the expansion or is one of the glossary's notes. It belongs to the
    expansion when the abbreviation has more parts than the Auflösung has
    words outside the parentheses -- then the abbreviation covers the
    parenthesized words too ('def. nat. s. c.' -> 'defectus natalium (de
    soluto et coniugata genitus)'). Otherwise it is a note on the context
    or the grammar ('nat.' -> 'natalis (def.)', 'ss.' -> 'sancti
    (Plural)') that must not end up in the text.

    Returns (Auflösung, note): the note is empty when the parentheses
    belong to the expansion (or there are none).
    """
    groups = FREE_PARENS.findall(aufloesung)
    if not groups:
        return aufloesung, ""
    outside = FREE_PARENS.sub(" ", aufloesung).split()
    if len(abbreviation.split(" ")) > len(outside):
        kept = FREE_PARENS.sub(lambda m: m.group(0)[1:-1], aufloesung)
        return re.sub(r"\s+", " ", kept).strip(), ""
    note = "; ".join(group[1:-1] for group in groups)
    return " ".join(outside), note


def normalize(rows: list[dict]) -> tuple[list[dict], dict[str, list]]:
    """Stage 4: whitespace, unusable rows, ";"-alternatives, "?" marker."""
    notes: dict[str, list] = {
        "dropped": [], "split": [], "unsure": [], "declined": [], "notes": []
    }
    result = []
    for row in rows:
        # the inherit stage ran already, so an empty Abkürzung means the
        # very first rows of the file were continuation rows -- impossible
        for column in ("Abkürzung", "Auflösung", *RG_COLUMNS):
            row[column] = re.sub(r"\s+", " ", row[column]).strip()

        if row["Auflösung"] in ("", "?"):
            notes["dropped"].append(
                f"{row['Abkürzung']!r}: no usable Auflösung "
                f"({row['Auflösung']!r})"
            )
            continue

        if row["Auflösung"].startswith("cf.:"):
            # a cross-reference to another entry, not an expansion
            notes["dropped"].append(
                f"{row['Abkürzung']!r}: cross-reference "
                f"({row['Auflösung']!r})"
            )
            continue

        if row["Auflösung"].endswith(";"):
            row[MULTI] = True
            row["Auflösung"] = row["Auflösung"].rstrip(";").strip()

        if row["Auflösung"].endswith(" ?"):
            row["Auflösung"] = row["Auflösung"][:-2].strip()
            note = "Auflösung im Abk.-Verzeichnis mit '?' markiert"
            row["Anmerkungen"] = (
                f"{row['Anmerkungen']}; {note}" if row["Anmerkungen"] else note
            )
            notes["unsure"].append(
                f"{row['Abkürzung']!r}: {row['Auflösung']!r}"
            )

        declined = re.fullmatch(
            r"(.*?) \((dekliniert|ungekürzt, dekl\.)\)", row["Auflösung"]
        )
        if declined:
            # the abbreviation stands for varying inflected forms, so the
            # fixed replacement of step 1 would often be wrong -> complex
            row["Auflösung"] = declined.group(1)
            row[FORCED] = True
            note = f"im Abk.-Verzeichnis: '({declined.group(2)})'"
            row["Anmerkungen"] = (
                f"{row['Anmerkungen']}; {note}" if row["Anmerkungen"] else note
            )
            notes["declined"].append(
                f"{row['Abkürzung']!r}: {row['Auflösung']!r}"
            )

        whole_parens = re.fullmatch(r"\(([^()]*)\)", row["Auflösung"])
        if whole_parens:
            row["Auflösung"] = whole_parens.group(1).strip()

        aufloesung, note = resolve_parentheses(row["Abkürzung"], row["Auflösung"])
        if note:
            row["Auflösung"] = aufloesung
            row["Anmerkungen"] = (
                f"{row['Anmerkungen']}; {note}" if row["Anmerkungen"] else note
            )
            notes["notes"].append(f"{row['Abkürzung']!r}: {note!r} -> Anmerkungen")
        elif aufloesung != row["Auflösung"]:
            notes["notes"].append(
                f"{row['Abkürzung']!r}: {row['Auflösung']!r} -> {aufloesung!r}"
            )
            row["Auflösung"] = aufloesung

        alternatives = [
            part.strip() for part in row["Auflösung"].split(";") if part.strip()
        ]
        if len(alternatives) > 1:
            notes["split"].append(
                f"{row['Abkürzung']!r}: {row['Auflösung']!r} -> "
                f"{alternatives}"
            )
        for alternative in alternatives:
            new = dict(row)
            new[MULTI] = row.get(MULTI, False) or len(alternatives) > 1
            new["Auflösung"] = alternative
            result.append(new)
    return result, notes


def rg_columns(rows: list[dict]) -> list[dict]:
    """
    Stage 5: reduce the RG1-9 cells and derive rows for other
    abbreviations they name.
    """
    result = []
    for row in rows:
        abbreviation = row["Abkürzung"]
        derived: dict[str, set[str]] = {}
        reduced = {}
        for column in RG_COLUMNS:
            found = False
            for value in (v.strip() for v in row[column].split(";")):
                if not value or value == row["Auflösung"]:
                    continue
                if value == abbreviation:
                    found = True
                elif "." in value:
                    derived.setdefault(value, set()).add(column)
                else:
                    # a written-out form: the cell cannot be reduced
                    row[RG_MISMATCH] = True
            reduced[column] = abbreviation if found else ""

        if row.get(RG_MISMATCH):
            result.append(row)  # keep the cells as they are
            continue

        row.update(reduced)
        result.append(row)
        for new_abbreviation, columns in sorted(derived.items()):
            new = dict(row)
            new["Abkürzung"] = new_abbreviation
            # derived abbreviations starting with a capital letter
            # abbreviate the capitalized form (names, saints, ...)
            if new_abbreviation[0].isupper() and row["Auflösung"][0].islower():
                new["Auflösung"] = (
                    row["Auflösung"][0].upper() + row["Auflösung"][1:]
                )
            for column in RG_COLUMNS:
                new[column] = new_abbreviation if column in columns else ""
            result.append(new)
    return result


WORD_VARIANT = re.compile(r"[A-Za-z]+[(\[][a-z/]+[)\]][A-Za-z]*")


def prefix_length(abbreviation: str, text: str) -> int:
    """Letters the abbreviation and the text share from the start."""
    core = re.sub(r"[. ]", "", abbreviation).lower()
    n = 0
    for a, b in zip(core, re.sub(r"[. ]", "", text).lower()):
        if a != b:
            break
        n += 1
    return n


def common_prefix_length(words: list[str]) -> int:
    n = 0
    for letters in zip(*words):
        if len(set(letters)) > 1:
            break
        n += 1
    return n


def choose_by_corpus(
    variants: list[str], search: "CorpusSearch | None"
) -> tuple[str, str]:
    """
    Pick the spelling of a word the RG actually uses more often, for the
    cases where the abbreviation does not tell the variants apart
    ('op.' fits both 'opidum' and 'oppidum').

    The variants are base forms, so they are searched as prefixes and the
    inflected forms count too. If none of them occurs, the search backs
    off one letter at a time -- but never past the letter where the
    variants start to differ, so what is compared stays the spelling.
    Returns (variant, reason) for the report.
    """
    if search is None:
        return variants[0], "no corpus search"
    floor = common_prefix_length(variants) + 1
    for cut in range(max(len(v) for v in variants), floor - 1, -1):
        counts = [search.count(rf"(?i)\b{re.escape(v[:cut])}") for v in variants]
        if not any(counts):
            continue
        best = max(counts)
        found = [v for v, c in zip(variants, counts) if c == best]
        reason = "corpus: " + ", ".join(
            f"{v[:cut]}* {c}x" for v, c in zip(variants, counts)
        )
        return found[0], reason
    return variants[0], "none of the variants occurs in the corpus"


def resolve_row(
    row: dict,
    search: "CorpusSearch | None" = None,
    reasons: list[str] | None = None,
) -> list[str]:
    """
    Stage 6 for one row: resolve the variant notation in the Auflösung
    against the row's abbreviation. Returns the list of Auflösung
    alternatives the row resolves to (usually one); `reasons` collects
    the spelling decisions the corpus had to make, for the report.
    """
    abbreviation = row["Abkürzung"]
    aufloesung = row["Auflösung"]

    # `/` between phrases: alternative expansions -- only when what
    # follows the slash is itself a phrase, otherwise the slash separates
    # word variants ('non obstante/obstantibus'). Slashes inside
    # parentheses belong to German notes and stay.
    plain = re.sub(r"\([^)]*\)", lambda m: "x" * len(m.group(0)), aufloesung)
    if any(" " in plain[i + 1:].split("/")[0].strip()
           for i, c in enumerate(plain) if c == "/"):
        return [part.strip() for part in aufloesung.split("/")]

    # spelling variants inside a word: op(p)idum, mart[iy]r
    words = aufloesung.split(" ")
    for i, word in enumerate(words):
        if WORD_VARIANT.fullmatch(word):
            variants = clean_morphology.expand_stem_variants(word).split("/")
            best = max(prefix_length(abbreviation, v) for v in variants)
            fitting = [
                v for v in variants if prefix_length(abbreviation, v) == best
            ]
            # the abbreviation decides if its letters single out one
            # variant ('renen.' -> 'renensis', not 'rhenensis'); if it
            # fits several ('op.'), the corpus decides
            if len(fitting) == 1:
                words[i] = fitting[0]
            else:
                words[i], reason = choose_by_corpus(fitting, search)
                if reasons is not None:
                    reasons.append(
                        f"{abbreviation!r}: {word!r} -> {words[i]!r} ({reason})"
                    )
    resolved = " ".join(words)

    # `/` between full words: one alternative if the abbreviation singles
    # it out, otherwise one row per alternative
    m = re.fullmatch(r"([A-Za-z ]*?)([A-Za-z]{3,}(?:/[A-Za-z]{3,})+)", resolved)
    if m:
        prefix, variants = m.group(1), m.group(2).split("/")
        best = max(prefix_length(abbreviation, prefix + v) for v in variants)
        chosen = [
            v for v in variants if prefix_length(abbreviation, prefix + v) == best
        ]
        # a longer shared prefix singles out one variant; a tie means the
        # abbreviation fits all of them
        return [prefix + v for v in (chosen if len(chosen) == 1 else variants)]

    return [reorder_words(abbreviation, resolved)]


def reorder_words(abbreviation: str, aufloesung: str) -> str:
    """
    Multi-word expansions follow the word order of the abbreviation
    ('ap. sed.' abbreviates 'apostolica sedes', although the glossary
    entry it derives from spells 'sedes apostolica'). If the abbreviation
    tokens match the Auflösung words as prefixes only in a different
    order, the words are reordered.
    """
    tokens = [t.rstrip(".").lower() for t in abbreviation.split(" ")]
    words = aufloesung.split(" ")
    if len(tokens) != len(words) or len(words) < 2:
        return aufloesung
    if all(w.lower().startswith(t) for t, w in zip(tokens, words)):
        return aufloesung  # already in the abbreviation's order

    reordered = []
    remaining = list(words)
    for token in tokens:
        matching = [w for w in remaining if w.lower().startswith(token)]
        if len(matching) != 1:
            return aufloesung  # no unambiguous assignment
        reordered.append(matching[0])
        remaining.remove(matching[0])
    return " ".join(reordered)


def resolve(
    rows: list[dict], search: "CorpusSearch | None" = None
) -> tuple[list[dict], list[str], list[str]]:
    """Stage 6: resolve variant notation (see resolve_row)."""
    result = []
    log: list[str] = []
    reasons: list[str] = []
    for row in rows:
        alternatives = resolve_row(row, search, reasons)
        if alternatives != [row["Auflösung"]]:
            log.append(
                f"{row['Abkürzung']!r}: {row['Auflösung']!r} -> "
                + " | ".join(map(repr, alternatives))
            )
        for alternative in alternatives:
            new = dict(row)
            new["Auflösung"] = alternative
            result.append(new)
    return result, log, reasons


def merge_duplicates(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Stage 7: merge rows with the same (Abkürzung, Auflösung). The
    Auflösung is compared case-insensitively (an alias entry may spell
    'sancti' where the derived 'SS.' row has 'Sancti'); a capitalized
    abbreviation keeps the capitalized spelling.
    """
    merged: dict[tuple[str, str], dict] = {}
    log = []
    for row in rows:
        key = (row["Abkürzung"], row["Auflösung"].lower())
        if key not in merged:
            merged[key] = row
            continue
        target = merged[key]
        if (row["Abkürzung"][0].isupper()
                and row["Auflösung"][0].isupper()
                and not target["Auflösung"][0].isupper()):
            target["Auflösung"] = row["Auflösung"]
        for column in COLUMNS:
            if not target[column]:
                target[column] = row[column]
            elif column in RG_COLUMNS and row[column]:
                values = [v.strip() for v in target[column].split(";")]
                for value in (v.strip() for v in row[column].split(";")):
                    if value not in values:
                        values.append(value)
                target[column] = "; ".join(values)
        for flag in (MULTI, RG_MISMATCH, FORCED, ADDED):
            if row.get(flag):
                target[flag] = True
        log.append(f"merged duplicate {key[0]!r} / {key[1]!r}")
    return list(merged.values()), log


def construct_query(abbreviation: str) -> str:
    """
    The corpus-search pattern for an abbreviation: periods are optional
    (they are sometimes missing in the text), the trailing period is
    dropped entirely so that also the bare letters count as an occurrence.
    """
    if abbreviation.endswith("."):
        abbreviation = abbreviation[:-1]
    escaped = re.escape(abbreviation).replace(r"\.", r"\.?")
    if escaped.endswith(r"\)"):
        return rf"\b{escaped}"
    return rf"\b{escaped}\b"


class CorpusSearch:
    """
    Volume lookup for abbreviation patterns in the RG corpus, with a
    persistent cache (the corpus is large and the queries are re-run on
    every extraction).
    """

    def __init__(self, corpus_path: str = CORPUS, cache_path: Path | None = None):
        self.corpus_path = corpus_path
        self.cache_path = cache_path or REVIEW_DIR / "corpus_cache.json"
        self.cache: dict[str, list[int]] = {}
        self.counts: dict[str, int] = {}
        self.text: pl.DataFrame | None = None
        if self.cache_path.exists():
            with open(self.cache_path, encoding="utf-8") as file:
                stored = json.load(file)
            if stored.get("corpus") == self._corpus_signature():
                self.cache = stored["queries"]
                self.counts = stored.get("counts", {})

    def _corpus_signature(self) -> str:
        stat = Path(self.corpus_path).stat()
        return f"{stat.st_size}-{int(stat.st_mtime)}"

    def _load_corpus(self) -> pl.DataFrame:
        if self.text is None:
            corpus = pl.read_csv(self.corpus_path)
            self.text = corpus.select(
                "volume",
                pl.coalesce(
                    pl.concat_str(
                        pl.col("header_no_tags").fill_null(""),
                        pl.col("regest_no_tags").fill_null(""),
                        separator="\n",
                    ),
                    pl.lit(""),
                ).alias("text"),
            )
        return self.text

    def volumes(self, query: str) -> list[int]:
        if query not in self.cache:
            text = self._load_corpus()
            found = (
                text.filter(pl.col("text").str.contains(query))
                .get_column("volume").unique().sort().to_list()
            )
            self.cache[query] = found
        return self.cache[query]

    def count(self, query: str) -> int:
        """Number of corpus entries the pattern occurs in."""
        if query not in self.counts:
            text = self._load_corpus()
            self.counts[query] = int(
                text.get_column("text").str.contains(query).sum()
            )
        return self.counts[query]

    def save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "corpus": self._corpus_signature(),
                    "queries": self.cache,
                    "counts": self.counts,
                },
                file,
            )


def corpus_check(
    rows: list[dict], search: CorpusSearch
) -> tuple[list[dict], list[str]]:
    """Stage 7: drop abbreviations that never occur, add `volumes`."""
    kept, dropped = [], []
    for row in rows:
        volumes = search.volumes(construct_query(row["Abkürzung"]))
        row["volumes"] = "|".join(str(v) for v in volumes)
        if volumes or row.get(ADDED):
            kept.append(row)
        else:
            dropped.append(
                f"{row['Abkürzung']!r} ({row['Auflösung']!r}): "
                f"not found in the corpus"
            )
    return kept, dropped


def split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Stage 9: partition into simple and complex abbreviations. An
    abbreviation is complex if any of its rows has several meanings
    (";" flag), an unreducible RG cell, or was forced by a correction --
    or if it has several meanings and one of them claims no volume at
    all: without volume information the other rows' claims cannot be
    trusted to be exclusive, so step 1 must not expand any of them.
    (Several meanings with volume claims are fine in simple.csv: step 1
    expands each volume only when exactly one row claims it.)
    """
    complex_abbreviations = {
        row["Abkürzung"]
        for row in rows
        if row.get(MULTI) or row.get(RG_MISMATCH) or row.get(FORCED)
        or ";" in row["Abkürzung"]
        or any(";" in row[column] for column in RG_COLUMNS)
    }
    claims: dict[str, list[set[str]]] = {}
    for row in rows:
        claims.setdefault(row["Abkürzung"], []).append(
            {column for column in RG_COLUMNS if row[column]}
        )
    for abbreviation, row_claims in claims.items():
        if len(row_claims) > 1 and not all(row_claims):
            complex_abbreviations.add(abbreviation)
    simple = [r for r in rows if r["Abkürzung"] not in complex_abbreviations]
    complex_ = [r for r in rows if r["Abkürzung"] in complex_abbreviations]
    return simple, complex_


def clean_complex(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Stage 10: the Auflösungen of complex.csv are the candidate texts of
    step 2. Moving the glossary's notes out of them (see
    resolve_parentheses) can make two entries identical ('dominus' and
    'dominus (nur Bd. 1 laut Abk-Verz.)'), so the rows are merged again.
    """
    return merge_duplicates(rows)


def sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (r["Abkürzung"].lower(), r["Auflösung"]))


def to_frame(rows: list[dict]) -> pl.DataFrame:
    """Rows -> DataFrame with the output schema (internal keys dropped)."""
    columns = COLUMNS + ["volumes"]
    data = {
        column: [row.get(column, "") or None for row in rows]
        for column in columns
    }
    return pl.DataFrame(data, schema={c: pl.String for c in columns})


# ---------------------------------------------------------------------------
# stage 11: validation against the corpus
# ---------------------------------------------------------------------------


def validate(
    simple: pl.DataFrame, complex_: pl.DataFrame, search: CorpusSearch
) -> dict[str, pl.DataFrame]:
    """
    Quality checks, each returned as a review table:

    - morphology_unattested: entries whose generated paradigm has no form
      at all in the corpus (a wrong stem or declension class produces
      forms that never occur)
    - aufloesung_unattested: Auflösung words that never occur written out
      in the corpus (the expansion cannot be checked against usage)
    - rg_volume_mismatch: rows claiming volume n (RGn filled) whose
      abbreviation is not actually found in volume n
    """
    from expand_rest import Vocabulary
    from paradigm import entry_forms

    corpus = pl.read_csv(CORPUS)
    vocabulary = Vocabulary.from_texts(
        corpus.get_column("header_no_tags").drop_nulls().to_list()
        + corpus.get_column("regest_no_tags").drop_nulls().to_list()
    )
    both = pl.concat([simple, complex_], how="vertical")

    morphology_rows = []
    aufloesung_rows = []
    seen_morphology = set()
    seen_words = set()
    for abbreviation, aufloesung, wortstamm, deklination in both.select(
        "Abkürzung", "Auflösung", "Wortstamm", "Deklination"
    ).iter_rows():
        for word in aufloesung_words(aufloesung):
            if word.lower() not in seen_words:
                seen_words.add(word.lower())
                if not vocabulary.counts[word]:
                    aufloesung_rows.append(
                        {"Abkürzung": abbreviation, "Auflösung": aufloesung,
                         "word": word}
                    )
        key = (aufloesung, wortstamm, deklination)
        if wortstamm is None or key in seen_morphology:
            continue
        seen_morphology.add(key)
        for word, forms in entry_forms(aufloesung, wortstamm, deklination) or []:
            if forms is None or len(forms) <= 1:
                continue
            attested = sorted(
                (form for form in forms if vocabulary.counts[form]),
                key=lambda form: -vocabulary.counts[form],
            )
            if not attested:
                morphology_rows.append(
                    {"Abkürzung": abbreviation, "Auflösung": aufloesung,
                     "word": word, "Wortstamm": wortstamm,
                     "Deklination": deklination, "forms": len(forms)}
                )

    mismatch_rows = []
    for row in both.iter_rows(named=True):
        for i in range(1, 10):
            cell = row[f"RG{i}"]
            if cell and str(i) not in (row["volumes"] or "").split("|"):
                mismatch_rows.append(
                    {"Abkürzung": row["Abkürzung"],
                     "Auflösung": row["Auflösung"], "volume": i,
                     "found_in": row["volumes"]}
                )

    return {
        "morphology_unattested": pl.DataFrame(
            morphology_rows or None,
            schema={"Abkürzung": pl.String, "Auflösung": pl.String,
                    "word": pl.String, "Wortstamm": pl.String,
                    "Deklination": pl.String, "forms": pl.Int64},
        ),
        "aufloesung_unattested": pl.DataFrame(
            aufloesung_rows or None,
            schema={"Abkürzung": pl.String, "Auflösung": pl.String,
                    "word": pl.String},
        ),
        "rg_volume_mismatch": pl.DataFrame(
            mismatch_rows or None,
            schema={"Abkürzung": pl.String, "Auflösung": pl.String,
                    "volume": pl.Int64, "found_in": pl.String},
        ),
    }


# ---------------------------------------------------------------------------
# --diff-old: compare with the outputs currently on disk
# ---------------------------------------------------------------------------


def diff_old(new: pl.DataFrame, old_path: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Row-level difference on the columns that identify an entry."""
    keys = ["Abkürzung", "Auflösung", *RG_COLUMNS, "volumes"]
    old = pl.read_csv(old_path, schema_overrides={c: pl.String for c in keys})
    new_keys = set(map(tuple, new.select(keys).fill_null("").iter_rows()))
    old_keys = set(map(tuple, old.select(keys).fill_null("").iter_rows()))
    added = pl.DataFrame(
        [dict(zip(keys, row)) for row in sorted(new_keys - old_keys)] or None,
        schema={c: pl.String for c in keys},
    )
    removed = pl.DataFrame(
        [dict(zip(keys, row)) for row in sorted(old_keys - new_keys)] or None,
        schema={c: pl.String for c in keys},
    )
    return added, removed


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def extract(write: bool, diff: bool) -> None:
    report: list[str] = ["# Extraction report", ""]

    def section(title: str, lines: list[str]) -> None:
        report.append(f"## {title} ({len(lines)})")
        report.extend(f"- {line}" for line in lines)
        report.append("")

    rows = load()
    report.append(f"Read {len(rows)} rows from {GLOSSARY}.")
    report.append("")

    rows, correction_log = apply_corrections(rows)
    section("Corrections applied", correction_log)

    rows = inherit(rows)

    rows, notes = normalize(rows)
    section("Rows dropped (no usable Auflösung)", notes["dropped"])
    section("Rows split (alternative expansions)", notes["split"])
    section("Unverified expansions ('?' moved to Anmerkungen)",
            notes["unsure"])
    section("Declined abbreviations (forced complex)", notes["declined"])
    section("Parenthesized parts resolved", notes["notes"])

    search = CorpusSearch()

    rows = rg_columns(rows)
    rows, resolve_log, spelling_log = resolve(rows, search)
    section("Variant notation resolved", resolve_log)
    section("Spelling decided by the corpus", spelling_log)
    rows, merge_log = merge_duplicates(rows)
    section("Duplicate rows merged", merge_log)

    rows, dropped = corpus_check(rows, search)
    search.save_cache()
    section("Abbreviations not found in the corpus (dropped)", dropped)

    simple_rows, complex_rows = split(rows)
    complex_rows, clean_log = clean_complex(complex_rows)
    section("Complex rows merged after stripping the notes", clean_log)
    simple = to_frame(sort_rows(simple_rows))
    complex_ = to_frame(sort_rows(complex_rows))
    report.append(
        f"Split: {simple.height} simple rows "
        f"({simple.get_column('Abkürzung').n_unique()} abbreviations), "
        f"{complex_.height} complex rows "
        f"({complex_.get_column('Abkürzung').n_unique()} abbreviations)."
    )
    report.append("")

    simple, simple_review = clean_morphology.clean_frame(simple, "simple")
    complex_, complex_review = clean_morphology.clean_frame(complex_, "complex")
    morphology_review = simple_review + complex_review
    section(
        "Morphology not automatically cleanable (kept as-is)",
        [f"[{r['file']}] {r['Abkürzung']!r} / {r['Auflösung']!r}: {r['issue']}"
         for r in morphology_review],
    )

    reviews = validate(simple, complex_, search)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    for name, frame in reviews.items():
        report.append(f"Validation `{name}`: {frame.height} rows "
                      f"-> data/review/{name}.csv")
        if write:
            frame.write_csv(REVIEW_DIR / f"{name}.csv")
    report.append("")

    if diff:
        for name, frame, path in (
            ("simple", simple, SIMPLE_OUT), ("complex", complex_, COMPLEX_OUT)
        ):
            added, removed = diff_old(frame, path)
            added.write_csv(REVIEW_DIR / f"diff_{name}_added.csv")
            removed.write_csv(REVIEW_DIR / f"diff_{name}_removed.csv")
            print(f"diff vs current {path}: {added.height} rows added, "
                  f"{removed.height} rows removed "
                  f"(data/review/diff_{name}_*.csv)")

    if write:
        simple.write_csv(SIMPLE_OUT)
        complex_.write_csv(COMPLEX_OUT)
        if morphology_review:
            pl.DataFrame(morphology_review).write_csv(
                REVIEW_DIR / "morphology_review.csv"
            )
        with open(REVIEW_DIR / "extraction_report.md", "w",
                  encoding="utf-8") as file:
            file.write("\n".join(report))
        print(f"Wrote {SIMPLE_OUT}, {COMPLEX_OUT} and data/review/.")
    else:
        print("\n".join(report))
        print("\ndry run -- pass --write to update the output files")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract data/simple.csv and data/complex.csv from the "
        "glossary export data/RGAbkVerz.csv."
    )
    parser.add_argument("--write", action="store_true",
                        help="write the outputs (default: dry run)")
    parser.add_argument("--diff-old", action="store_true",
                        help="compare with the simple.csv/complex.csv "
                        "currently on disk")
    arguments = parser.parse_args()
    extract(write=arguments.write, diff=arguments.diff_old)


if __name__ == "__main__":
    main()
