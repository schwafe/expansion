#!/usr/bin/env python3
"""
Test suite for step 1 (the rule-based expansion).

Covers:
- the assumption that a row without volume columns applies to every volume,
  and that it is only made where the abbreviation has a single reading
- which rows a volume may apply at all
- the substitution: multi-word abbreviations with and without their spaces,
  longest first, and no expansion of what is already expanded
- the counting the report is built from
"""

import polars as pl

from expand_simple import (
    abbreviation_counts,
    apply_to_every_volume,
    count_abbreviations,
    expand_volume,
    rules_of_volume,
    unambiguous,
)

VOLUME_COLUMNS = [f"RG{volume}" for volume in range(1, 10)]


def rules(*entries) -> pl.DataFrame:
    """A glossary of (abbreviation, expansion, volumes) rows."""
    frame = pl.DataFrame(
        {
            "Abkürzung": [entry[0] for entry in entries],
            "Auflösung": [entry[1] for entry in entries],
        }
    )
    columns = []
    for volume, name in enumerate(VOLUME_COLUMNS, start=1):
        columns.append(
            pl.Series(
                name,
                [entry[0] if volume in entry[2] else None for entry in entries],
                dtype=pl.String,
            )
        )
    return frame.with_columns(columns).with_columns(
        pl.col("Abkürzung").str.split(" ").list.len().alias("abbr_parts")
    )


def texts(*values) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "volume": [1] * len(values),
            "header_no_tags": list(values),
            "regest_no_tags": [None] * len(values),
        },
        schema={"volume": pl.Int64, "header_no_tags": pl.String, "regest_no_tags": pl.String},
    )


class TestApplyToEveryVolume:
    def test_a_lone_row_without_volumes_is_read_as_every_volume(self):
        filled = apply_to_every_volume(rules(("dioc.", "diocesis", [])))
        assert filled.select(VOLUME_COLUMNS).row(0) == tuple(["dioc."] * 9)

    def test_a_row_with_siblings_is_left_alone(self):
        """There the volume columns are what tells the readings apart."""
        filled = apply_to_every_volume(
            rules(("d.", "datum", []), ("d.", "dominus", [3]))
        )
        assert filled.select(VOLUME_COLUMNS).row(0) == tuple([None] * 9)
        assert filled.select("RG3").row(1) == ("d.",)

    def test_a_row_that_names_its_volumes_keeps_them(self):
        filled = apply_to_every_volume(rules(("eccl.", "ecclesia", [2, 5])))
        assert filled.get_column("RG2").item() == "eccl."
        assert filled.get_column("RG4").item() is None


class TestWhichRulesApply:
    def test_only_the_rows_of_the_volume(self):
        glossary = rules(("eccl.", "ecclesia", [1]), ("mon.", "monasterium", [2]))
        assert rules_of_volume(glossary, 1).get_column("Abkürzung").to_list() == ["eccl."]

    def test_an_ambiguous_abbreviation_is_left_to_step_2(self):
        glossary = rules(("d.", "datum", [1]), ("d.", "dominus", [1]), ("mon.", "monasterium", [1]))
        assert unambiguous(rules_of_volume(glossary, 1)).get_column("Abkürzung").to_list() == ["mon."]


class TestExpandVolume:
    def test_the_abbreviation_is_replaced(self):
        expanded = expand_volume(texts("eccl. mai."), rules(("eccl.", "ecclesia", [1])))
        assert expanded.get_column("header_no_tags").item() == "ecclesia mai."

    def test_the_spaces_of_a_multi_word_abbreviation_are_optional(self):
        glossary = rules(("e. m.", "extra muros", [1]))
        expanded = expand_volume(texts("in e. m.", "in e.m."), glossary)
        assert expanded.get_column("header_no_tags").to_list() == ["in extra muros", "in extra muros"]

    def test_a_longer_abbreviation_wins_when_it_comes_first(self):
        """load_rules sorts by length, so the whole is resolved before its parts."""
        glossary = rules(("s. p. d.", "sine perdatum", [1]), ("s.", "sanctus", [1]))
        expanded = expand_volume(texts("de s. p. d. S"), glossary.sort("abbr_parts", descending=True))
        assert expanded.get_column("header_no_tags").item() == "de sine perdatum S"

    def test_an_expansion_is_never_expanded_again(self):
        """No expansion contains a period, so no rule can match one."""
        glossary = rules(("mon.", "monasterium", [1]), ("mo.", "mons", [1]))
        expanded = expand_volume(texts("mon. s."), glossary)
        assert expanded.get_column("header_no_tags").item() == "monasterium s."

    def test_a_dollar_in_the_expansion_is_not_a_capture_reference(self):
        expanded = expand_volume(texts("m. arg."), rules(("m.", "$ marca", [1])))
        assert expanded.get_column("header_no_tags").item() == "$ marca arg."

    def test_a_word_that_only_starts_like_the_abbreviation_is_untouched(self):
        expanded = expand_volume(texts("ecclesia eccl."), rules(("eccl.", "ecclesia", [1])))
        assert expanded.get_column("header_no_tags").item() == "ecclesia ecclesia"


class TestCounting:
    def test_abbreviations_are_words_followed_by_a_period(self):
        assert count_abbreviations(texts("eccl. mai. domus")) == 2

    def test_multi_word_abbreviations_are_counted_as_well_as_their_parts(self):
        counts = abbreviation_counts(texts("par. eccl. s."))
        found = dict(zip(counts.get_column("abbreviation"), counts.get_column("count")))
        assert found["par."] == 1
        assert found["par. eccl."] == 1
        assert found["par. eccl. s."] == 1

    def test_the_number_of_parts_is_recorded(self):
        counts = abbreviation_counts(texts("par. eccl."))
        parts = dict(zip(counts.get_column("abbreviation"), counts.get_column("parts")))
        assert parts["par."] == 1
        assert parts["par. eccl."] == 2
