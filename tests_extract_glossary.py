#!/usr/bin/env python3
"""
Test suite for step 0 (extracting the glossary from data/RGAbkVerz.csv).

Covers every stage of extract_glossary.py on toy rows:
- corrections (application, logging, and failing on stale entries)
- inheritance of the abbreviation to continuation rows
- normalization (whitespace, unusable rows, ";"-alternatives, "?" and
  "(dekliniert)" markers)
- reduction of the RG columns and derived abbreviations
- resolution of the variant notation against the abbreviation
- merging of duplicate rows
- the corpus query and the existence filter
- the simple/complex split
- cleaning of the complex Auflösungen
- integration with clean_morphology.clean_frame
"""

import pytest

import extract_glossary as eg
from extract_glossary import Correction


def row(**overrides):
    return eg.empty_row() | overrides


class TestCorrections:
    def test_set_and_log(self):
        rows = [row(Abkürzung="facult.", Auflösung="facultas", RG1="facult")]
        corrections = [Correction(reason="missing period",
                                  match={"Abkürzung": "facult."},
                                  set={"RG1": "facult."})]

        result, log = eg.apply_corrections(rows, corrections, additions=[])

        assert result[0]["RG1"] == "facult."
        assert "missing period" in log[0]

    def test_delete_and_add(self):
        rows = [row(Abkürzung="k.", Auflösung="korrigiert"),
                row(Abkürzung="lim.", Auflösung="limina (appl.)")]
        corrections = [
            Correction(reason="inexistent", match={"Abkürzung": "k."},
                       delete=True),
            Correction(reason="bundles two abbreviations",
                       match={"Abkürzung": "lim."},
                       set={"Auflösung": "limina"},
                       add=[{"Abkürzung": "lim. appl.",
                             "Auflösung": "limina apostolorum"}]),
        ]

        result, log = eg.apply_corrections(rows, corrections, additions=[])

        assert [r["Abkürzung"] for r in result] == ["lim.", "lim. appl."]
        assert result[0]["Auflösung"] == "limina"

    def test_stale_correction_fails(self):
        rows = [row(Abkürzung="abc.", Auflösung="abc")]
        corrections = [Correction(reason="gone",
                                  match={"Abkürzung": "nonexistent."})]

        with pytest.raises(SystemExit, match="matched 0 rows"):
            eg.apply_corrections(rows, corrections, additions=[])

    def test_additions_are_flagged(self):
        result, log = eg.apply_corrections(
            [], [], additions=[("found in the texts",
                                {"Abkürzung": "x.", "Auflösung": "xus"})]
        )
        assert result[0][eg.ADDED]

    def test_real_corrections_apply_to_the_real_glossary(self):
        rows = eg.load()
        rows, log = eg.apply_corrections(rows)
        assert len(log) >= len(eg.CORRECTIONS)


class TestInherit:
    def test_continuation_rows(self):
        rows = [row(Abkürzung="a.", Auflösung="annus"),
                row(Auflösung="argentum"),
                row(Abkürzung="abb.", Auflösung="abbas")]
        assert [r["Abkürzung"] for r in eg.inherit(rows)] == [
            "a.", "a.", "abb."
        ]


class TestNormalize:
    def test_whitespace_and_unusable(self):
        rows = [row(Abkürzung="a. ", Auflösung="?"),
                row(Abkürzung="omn.  ss.", Auflösung="Omnium  sanctorum")]

        result, notes = eg.normalize(rows)

        assert len(result) == 1
        assert result[0]["Abkürzung"] == "omn. ss."
        assert result[0]["Auflösung"] == "Omnium sanctorum"
        assert len(notes["dropped"]) == 1

    def test_trailing_semicolon_marks_multi(self):
        rows = [row(Abkürzung="abol.", Auflösung="abolere;")]
        result, notes = eg.normalize(rows)
        assert result[0]["Auflösung"] == "abolere"
        assert result[0][eg.MULTI]

    def test_internal_semicolon_splits(self):
        rows = [row(Abkürzung="adh.", Auflösung="adherens; adherentes")]
        result, notes = eg.normalize(rows)
        assert [r["Auflösung"] for r in result] == ["adherens", "adherentes"]
        assert all(r[eg.MULTI] for r in result)

    def test_question_mark_moves_to_anmerkungen(self):
        rows = [row(Abkürzung="off. tab.", Auflösung="tabellionatus officium ?")]
        result, _ = eg.normalize(rows)
        assert result[0]["Auflösung"] == "tabellionatus officium"
        assert "?" in result[0]["Anmerkungen"]

    def test_declined_forces_complex(self):
        rows = [row(Abkürzung="fratr.", Auflösung="frater (dekliniert)")]
        result, notes = eg.normalize(rows)
        assert result[0]["Auflösung"] == "frater"
        assert result[0][eg.FORCED]
        assert "dekliniert" in result[0]["Anmerkungen"]

    def test_whole_parentheses_are_stripped(self):
        rows = [row(Abkürzung="opid.", Auflösung="(opidum)")]
        result, _ = eg.normalize(rows)
        assert result[0]["Auflösung"] == "opidum"

    def test_parenthesized_note_moves_to_anmerkungen(self):
        rows = [row(Abkürzung="nat.", Auflösung="natalis (def.)"),
                row(Abkürzung="ss.", Auflösung="sancti (Plural)"),
                row(Abkürzung="sign.", Auflösung="(sola) signatura"),
                row(Abkürzung="def. nat.",
                    Auflösung="defectus natalium (de soluto et coniugata "
                              "genitus)")]

        result, notes = eg.normalize(rows)

        assert [r["Auflösung"] for r in result] == [
            "natalis", "sancti", "signatura", "defectus natalium",
        ]
        assert result[0]["Anmerkungen"] == "def."
        assert len(notes["notes"]) == 4

    def test_parentheses_covered_by_the_abbreviation_stay(self):
        rows = [row(Abkürzung="def. nat. s. c.",
                    Auflösung="defectus natalium (de soluto et coniugata "
                              "genitus)")]

        result, _ = eg.normalize(rows)

        assert result[0]["Auflösung"] == (
            "defectus natalium de soluto et coniugata genitus"
        )
        assert result[0]["Anmerkungen"] == ""


class TestRgColumns:
    def test_cells_are_reduced_to_own_abbreviation(self):
        rows = [row(Abkürzung="abb.", Auflösung="abbas",
                    RG1="abb.", RG2="abb.; abbas", RG3="")]
        result = eg.rg_columns(rows)
        assert len(result) == 1
        assert (result[0]["RG1"], result[0]["RG2"], result[0]["RG3"]) == (
            "abb.", "abb.", ""
        )

    def test_other_abbreviations_spawn_derived_rows(self):
        rows = [row(Abkürzung="apr.", Auflösung="aprilis",
                    RG4="apr.; april.", RG5="apr.")]
        result = eg.rg_columns(rows)
        assert [(r["Abkürzung"], r["RG4"], r["RG5"]) for r in result] == [
            ("apr.", "apr.", "apr."), ("april.", "april.", ""),
        ]

    def test_written_out_form_marks_mismatch(self):
        rows = [row(Abkürzung="abol.", Auflösung="abolere", RG1="abolitio")]
        result = eg.rg_columns(rows)
        assert result[0][eg.RG_MISMATCH]
        assert result[0]["RG1"] == "abolitio"  # kept as it is

    def test_derived_capitalized_abbreviation_capitalizes(self):
        rows = [row(Abkürzung="apl.", Auflösung="apostolus", RG1="Ap.")]
        result = eg.rg_columns(rows)
        assert (result[1]["Abkürzung"], result[1]["Auflösung"]) == (
            "Ap.", "Apostolus"
        )


class TestResolve:
    def test_bracket_variants_follow_the_abbreviation(self):
        assert eg.resolve_row(row(Abkürzung="opp.", Auflösung="op(p)idum")) \
            == ["oppidum"]
        assert eg.resolve_row(row(Abkürzung="op.", Auflösung="op(p)idum")) \
            == ["opidum"]  # tie -> the plain variant
        assert eg.resolve_row(row(Abkürzung="mart.", Auflösung="mart[iy]r")) \
            == ["martir"]

    def test_word_alternatives(self):
        # the abbreviation singles out one variant
        assert eg.resolve_row(
            row(Abkürzung="succust.", Auflösung="subcustos/succustos")
        ) == ["succustos"]
        # a tie keeps all of them (one row per alternative)
        assert eg.resolve_row(
            row(Abkürzung="lit.", Auflösung="lite/litis")
        ) == ["lite", "litis"]
        # a preceding word is part of every alternative
        assert eg.resolve_row(
            row(Abkürzung="n. o.", Auflösung="non obstante/obstantibus")
        ) == ["non obstante", "non obstantibus"]

    def test_phrase_alternatives(self):
        assert eg.resolve_row(
            row(Abkürzung="s. e. d.",
                Auflösung="sub eodem dato/sub eadem data")
        ) == ["sub eodem dato", "sub eadem data"]

    def test_word_order_follows_the_abbreviation(self):
        assert eg.resolve_row(
            row(Abkürzung="ap. sed.", Auflösung="sedes apostolica")
        ) == ["apostolica sedes"]
        assert eg.resolve_row(
            row(Abkürzung="commun. serv.", Auflösung="servitium commune")
        ) == ["commune servitium"]
        # already in order -> unchanged
        assert eg.resolve_row(
            row(Abkürzung="m. a. p.", Auflösung="marca argenti puri")
        ) == ["marca argenti puri"]
        # ambiguous tokens match in any order -> the glossary order stays
        assert eg.resolve_row(
            row(Abkürzung="s. s.", Auflösung="sedes sancta")
        ) == ["sedes sancta"]

    def test_slash_inside_parentheses_stays(self):
        aufloesung = ("datum (nur Bd. 6 laut Abk-Verz. sowie in Verbindung "
                      "mit d. d./s. e. d./ s. d.)")
        assert eg.resolve_row(row(Abkürzung="dat.", Auflösung=aufloesung)) \
            == [aufloesung]


class TestMergeDuplicates:
    def test_rg_cells_are_united(self):
        rows = [row(Abkürzung="april.", Auflösung="aprilis", RG4="april."),
                row(Abkürzung="april.", Auflösung="aprilis",
                    Übersetzung="April", Anmerkungen="siehe apr.")]

        result, log = eg.merge_duplicates(rows)

        assert len(result) == 1
        assert result[0]["RG4"] == "april."
        assert result[0]["Übersetzung"] == "April"
        assert len(log) == 1

    def test_flags_survive(self):
        rows = [row(Abkürzung="x.", Auflösung="xus"),
                row(Abkürzung="x.", Auflösung="xus", **{eg.MULTI: True})]
        result, _ = eg.merge_duplicates(rows)
        assert result[0][eg.MULTI]

    def test_case_insensitive_with_capitalized_abbreviation(self):
        rows = [row(Abkürzung="SS.", Auflösung="sancti"),
                row(Abkürzung="SS.", Auflösung="Sancti", RG1="SS.")]
        result, _ = eg.merge_duplicates(rows)
        assert len(result) == 1
        assert result[0]["Auflösung"] == "Sancti"
        assert result[0]["RG1"] == "SS."


class TestCorpus:
    def test_query_makes_periods_optional(self):
        assert eg.construct_query("eccl.") == r"\beccl\b"
        assert eg.construct_query("def. nat.") == r"\bdef\.?\ nat\b"

    def test_query_of_parenthesized_abbreviation(self):
        assert eg.construct_query("def. nat. (s. c.)").endswith(r"\)")

    def test_existence_filter(self):
        class FakeSearch:
            def volumes(self, query):
                return [1, 4] if "eccl" in query else []

        rows = [row(Abkürzung="eccl.", Auflösung="ecclesia"),
                row(Abkürzung="xyz.", Auflösung="xyzus"),
                row(Abkürzung="abc.", Auflösung="abcus", **{eg.ADDED: True})]

        kept, dropped = eg.corpus_check(rows, FakeSearch())

        assert [r["Abkürzung"] for r in kept] == ["eccl.", "abc."]
        assert kept[0]["volumes"] == "1|4"
        assert len(dropped) == 1


class TestSplit:
    def test_multi_and_mismatch_force_complex(self):
        rows = [row(Abkürzung="abol.", Auflösung="abolere",
                    **{eg.MULTI: True}),
                row(Abkürzung="abol.", Auflösung="abolitio"),
                row(Abkürzung="abb.", Auflösung="abbas", RG1="abb.")]

        simple, complex_ = eg.split(rows)

        assert [r["Abkürzung"] for r in simple] == ["abb."]
        # all rows of a complex abbreviation move together
        assert [r["Abkürzung"] for r in complex_] == ["abol.", "abol."]

    def test_duplicate_rows_alone_stay_simple(self):
        # volume-specific meanings (like a. -> annus/argentum) are handled
        # by step 1 per volume and stay simple -- even when the claims
        # overlap (step 1 skips contested volumes)
        rows = [row(Abkürzung="a.", Auflösung="annus", RG1="a.", RG6="a."),
                row(Abkürzung="a.", Auflösung="argentum", RG6="a.")]
        simple, complex_ = eg.split(rows)
        assert len(simple) == 2 and not complex_

    def test_meaning_without_volume_claims_forces_complex(self):
        # 'deputatus' claims no volume, so 'deputare' cannot be trusted
        # to be the only expansion anywhere
        rows = [row(Abkürzung="deput.", Auflösung="deputare", RG2="deput."),
                row(Abkürzung="deput.", Auflösung="deputatus")]
        simple, complex_ = eg.split(rows)
        assert not simple and len(complex_) == 2

    def test_clean_complex_merges_rows_the_notes_made_identical(self):
        # both rows come out of normalize() as 'dominus'
        rows = [row(Abkürzung="d.", Auflösung="dominus", RG1="d."),
                row(Abkürzung="d.", Auflösung="dominus",
                    Anmerkungen="nur Bd. 1 laut Abk-Verz.")]
        cleaned, log = eg.clean_complex(rows)
        assert len(cleaned) == 1 and cleaned[0]["RG1"] == "d."
        assert len(log) == 1


class TestMorphologyIntegration:
    def test_clean_frame_on_extracted_rows(self):
        import clean_morphology

        frame = eg.to_frame([
            row(Abkürzung="abba.", Auflösung="abbatissa",
                Wortstamm="abbatiss -(a)e", Deklination="a"),
            row(Abkürzung="kal.", Auflösung="kalendae",
                Wortstamm="mystery", Deklination="???"),
        ])

        cleaned, review = clean_morphology.clean_frame(frame, "simple")

        assert cleaned.get_column("Wortstamm")[0] == "abbatiss -e"
        assert len(review) == 1
        assert review[0]["file"] == "simple"


class TestFrame:
    def test_internal_flags_are_dropped(self):
        frame = eg.to_frame([row(Abkürzung="a.", Auflösung="annus",
                                 volumes="1|2", **{eg.MULTI: True})])
        assert eg.MULTI not in frame.columns
        assert frame.get_column("volumes")[0] == "1|2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
