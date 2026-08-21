#!/usr/bin/env python3
"""
Step 1: expanding the abbreviations that have exactly one reading.

The Abkürzungsverzeichnis (`data/simple.csv`, written by step 0) lists for every
volume of the RG which abbreviations it uses and how they are resolved. Where a
volume knows exactly one Auflösung for an abbreviation, no judgement is needed
and the expansion is a plain substitution -- that is what this step does, for
the whole RG rather than for a subset. Everything it leaves standing is either
ambiguous (several Auflösungen: step 2 chooses among them) or not in the
glossary at all (step 3 mines the corpus for it).

Two decisions are worth stating, because neither is forced by the data:

- **Volume columns.** A row whose RG1-RG9 columns are all empty and whose
  abbreviation appears nowhere else in the glossary is taken to apply to every
  volume. The glossary simply does not record a volume for those entries, and
  since no other row claims the abbreviation, no reading can be lost by it.
  A row that is empty *and* has siblings is left alone -- there the volume
  columns are what distinguishes the readings.
- **Volume 10.** The glossary has no rules for it, so it is dropped here and
  does not reach the later steps.

The substitution uses `multiple_choice.occurrence_pattern`, the same pattern
step 2 marks its occurrences with, so both steps agree on where an abbreviation
begins and ends (in particular on the optional spaces inside a multi-word
abbreviation, `e. m.` and `e.m.`). Longer abbreviations are applied first, so
`s. p. d.` is resolved as a whole and never as three separate parts.

Usage:
    python expand_simple.py            # dry run, prints the report
    python expand_simple.py --write    # write data/once_expanded.csv
"""

import argparse
from pathlib import Path

import polars as pl

from helper_functions import find_overlapping_matches
from multiple_choice import occurrence_pattern

DATA_DIR = Path("data")
REVIEW_DIR = DATA_DIR / "review"
SIMPLE = DATA_DIR / "simple.csv"
COMPLEX = DATA_DIR / "complex.csv"
DIOCESES = DATA_DIR / "dioceses.csv"
RG = DATA_DIR / "RG_header_sublemma_all.csv"
OUTPUT = DATA_DIR / "once_expanded.csv"
REPORT = REVIEW_DIR / "expansion_report.md"

# the volumes the glossary has rules for; volume 10 is dropped
VOLUMES = range(1, 10)

# the columns of the RG the later steps work on
RG_COLUMNS = ["volume", "nr_RG", "nr_suffix", "header_no_tags", "regest_no_tags", "id_RG_all"]
TEXT_COLUMNS = ["header_no_tags", "regest_no_tags"]

# an abbreviation for the counting: a word followed by a period, up to five of
# them in a row, so that `o. s. Ben.` is counted as one and as its parts
ABBREVIATION = r"\b(\w+\.)"
MULTIWORD = [r"\b(" + r"\ ?".join([r"\w+\."] * parts) + ")" for parts in range(2, 6)]


# --------------------------------------------------------------------------
# the rules
# --------------------------------------------------------------------------

def load_rules(simple: Path = SIMPLE, dioceses: Path = DIOCESES) -> pl.DataFrame:
    """
    The glossary plus the diocese adjectives, longest abbreviation first.

    `dioceses.csv` has only the two columns; the diagonal concat fills the rest
    with null, which is what `apply_to_every_volume` then reads as "every
    volume" -- the diocese abbreviations are unique and have no volume columns.
    """
    rules = pl.concat(
        [
            pl.read_csv(simple),
            pl.read_csv(dioceses).rename({"abbreviation": "Abkürzung", "expansion": "Auflösung"}),
        ],
        how="diagonal",
    )
    return rules.with_columns(
        pl.col("Abkürzung").str.split(" ").list.len().alias("abbr_parts")
    ).sort("abbr_parts", descending=True)


def apply_to_every_volume(rules: pl.DataFrame) -> pl.DataFrame:
    """
    Read a row without volume columns as applying to every volume.

    Only for abbreviations that occur once in the glossary: where several rows
    share an abbreviation, the volume columns are what tells the readings
    apart, and filling them in would make every one of them apply everywhere.
    """
    everywhere = (~pl.col("Abkürzung").is_duplicated()) & pl.all_horizontal(
        pl.col("^RG[1-9]$").is_null()
    )
    return rules.with_columns(
        pl.when(everywhere).then(pl.col("Abkürzung")).otherwise(pl.col(f"RG{volume}")).alias(f"RG{volume}")
        for volume in VOLUMES
    )


def rules_of_volume(rules: pl.DataFrame, volume: int) -> pl.DataFrame:
    """The rows this volume uses -- its column repeats the abbreviation."""
    return rules.filter(pl.col(f"^RG{volume}$").str.contains(pl.col("Abkürzung")))


def unambiguous(volume_rules: pl.DataFrame) -> pl.DataFrame:
    """The rows this step may apply: one Auflösung, so nothing to choose."""
    return volume_rules.filter(~pl.col("Abkürzung").is_duplicated())


# --------------------------------------------------------------------------
# the expansion
# --------------------------------------------------------------------------

def expand_volume(texts: pl.DataFrame, volume_rules: pl.DataFrame) -> pl.DataFrame:
    """Substitute every rule of one volume into the header and the regests."""
    for rule in volume_rules.iter_rows(named=True):
        pattern = occurrence_pattern(rule["Abkürzung"])
        # `$` in a replacement is a capture reference for the regex engine
        expansion = rule["Auflösung"].replace("$", "$$")
        texts = texts.with_columns(
            pl.col(column).str.replace_all(pattern, expansion) for column in TEXT_COLUMNS
        )
    return texts


def expand(rg: pl.DataFrame, rules: pl.DataFrame) -> pl.DataFrame:
    """
    The whole RG with its unambiguous abbreviations resolved.

    No expansion contains a period and every abbreviation ends in one, so an
    expansion can never be expanded again and the order of the rules within a
    volume does not matter -- except for length, which `load_rules` sorts by.
    """
    volumes = [
        expand_volume(rg.filter(pl.col("volume") == volume), unambiguous(rules_of_volume(rules, volume)))
        for volume in VOLUMES
    ]
    return pl.concat(volumes)


# --------------------------------------------------------------------------
# measuring what is left
# --------------------------------------------------------------------------

def count_abbreviations(texts: pl.DataFrame) -> int:
    """How many words followed by a period the texts still contain."""
    counts = texts.select(pl.col(column).str.count_matches(ABBREVIATION).sum() for column in TEXT_COLUMNS)
    return sum(value for value in counts.row(0) if value is not None)


def abbreviation_counts(texts: pl.DataFrame) -> pl.DataFrame:
    """Every abbreviation with its frequency, multi-word ones included."""
    found = texts.with_columns(
        [pl.col(column).str.extract_all(ABBREVIATION).alias(f"1{column}") for column in TEXT_COLUMNS]
        + [
            pl.col(column)
            .map_elements(
                lambda text, pattern=pattern: find_overlapping_matches(text, pattern),
                return_dtype=pl.List(pl.String),
            )
            .alias(f"{parts}{column}")
            for parts, pattern in enumerate(MULTIWORD, start=2)
            for column in TEXT_COLUMNS
        ]
    )
    columns = [name for name in found.columns if name[0].isdigit()]
    pieces = [found.get_column(name).explode(empty_as_null=True).drop_nulls() for name in columns]
    abbreviations = pl.concat(
        [piece.rename("abbreviation") for piece in pieces if len(piece)]
    )
    return (
        abbreviations
        .value_counts()
        .with_columns(pl.col("abbreviation").str.split(" ").list.len().alias("parts"))
        .sort("count", descending=True)
    )


def unrealised_potential(left_over: pl.DataFrame, *glossaries: Path) -> pl.DataFrame:
    """
    What is still abbreviated although the glossary knows the abbreviation.

    These are the entries with more than one reading (or with the volume
    columns against them): steps 2 and 3 have to decide them one occurrence at
    a time, and every one of them that the glossary could resolve for a whole
    volume would be won back here.
    """
    known = pl.concat(
        [pl.read_csv(path).select("Abkürzung").unique() for path in glossaries]
    ).unique()
    return (
        left_over.rename({"abbreviation": "Abkürzung"})
        .join(known, on="Abkürzung", how="inner")
        .sort("count", descending=True)
    )


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def render_report(rules: pl.DataFrame, before: pl.DataFrame, after: pl.DataFrame) -> str:
    original, left_over = abbreviation_counts(before), abbreviation_counts(after)
    total_before, total_after = count_abbreviations(before), count_abbreviations(after)

    lines = [
        "# Step 1: the rule-based expansion",
        "",
        f"{total_before} abbreviations in volumes {VOLUMES.start}-{VOLUMES.stop - 1} of the RG, "
        f"{total_after} left after the substitution "
        f"({1 - total_after / total_before:.1%} resolved). Volume 10 is dropped: "
        "the glossary has no rules for it.",
        "",
        "## Rules per volume",
        "",
        "Only an abbreviation with a single Auflösung can be substituted; the "
        "ambiguous ones are left for step 2.",
        "",
        "| volume | rules of the volume | applied (one reading) | left to step 2 |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for volume in VOLUMES:
        of_volume = rules_of_volume(rules, volume)
        applied = unambiguous(of_volume)
        lines.append(
            f"| {volume} | {len(of_volume)} | {len(applied)} | {len(of_volume) - len(applied)} |"
        )

    lines += [
        "",
        "## What is left",
        "",
        "The most frequent abbreviations before and after the substitution.",
        "",
        "| abbreviation | before | abbreviation | after |",
        "| --- | ---: | --- | ---: |",
    ]
    for first, second in zip(original.head(20).iter_rows(named=True), left_over.head(20).iter_rows(named=True)):
        lines.append(
            f"| `{first['abbreviation']}` | {first['count']} | "
            f"`{second['abbreviation']}` | {second['count']} |"
        )

    multiword = left_over.filter(pl.col("parts") > 1).head(10)
    lines += [
        "",
        "The most frequent of them that are multi-word:",
        "",
        ", ".join(f"`{row['abbreviation']}` ({row['count']})" for row in multiword.iter_rows(named=True)),
    ]

    potential = unrealised_potential(left_over, SIMPLE, COMPLEX)
    lines += [
        "",
        "## What a clearer glossary entry would gain",
        "",
        "Abbreviations that are still standing although the glossary knows them: "
        "they have more than one reading, so steps 2 and 3 have to decide them "
        f"occurrence by occurrence. {potential['count'].sum()} occurrences in total.",
        "",
        "| abbreviation | occurrences |",
        "| --- | ---: |",
    ]
    for row in potential.head(20).iter_rows(named=True):
        lines.append(f"| `{row['Abkürzung']}` | {row['count']} |")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def expand_simple(rg_path: Path, out: Path, write: bool) -> pl.DataFrame:
    rules = apply_to_every_volume(load_rules())
    rg = pl.read_csv(rg_path).select(RG_COLUMNS).sort(["volume", "nr_RG", "nr_suffix"])
    expanded = expand(rg, rules)

    report = render_report(rules, rg.filter(pl.col("volume") != 10), expanded)
    print(report)

    if write:
        expanded.write_csv(out)
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(report, encoding="utf-8")
        print(f"Wrote {out} ({len(expanded)} rows) and {REPORT}.")
    else:
        print(f"dry run -- pass --write to update {out}")
    return expanded


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Expand the abbreviations that have a single glossary reading."
    )
    parser.add_argument("--rg", type=Path, default=RG, help=f"the RG texts (default: {RG})")
    parser.add_argument("--out", type=Path, default=OUTPUT, help=f"where to write (default: {OUTPUT})")
    parser.add_argument("--write", action="store_true", help=f"write {OUTPUT} (default: dry run)")
    arguments = parser.parse_args()
    expand_simple(arguments.rg, arguments.out, arguments.write)


if __name__ == "__main__":
    main()
