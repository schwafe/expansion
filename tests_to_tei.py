#!/usr/bin/env python3
"""
Test suite for step 6 (writing both readings as one TEI document).

Covers:
- what becomes a <choice>, a bare <abbr> and plain text
- the two readings, and the round-trip that guards the source text
- the material between words that only one reading has (punctuation the
  expansion adds, spacing it changes)
- the cases the tokenizer cannot decide on its own: a sentence-final word, a
  folio mark glued to a number, several abbreviations sharing one expansion
- the @resp attribution
"""

import pytest

from to_tei import (Segment, attribute, is_shelfmark, mark_up, readings,
                    render, token_spans)

KNOWN = {"eccl.", "s.", "op.", "aep.", "etc.", "d.", "p.", "mai."}
ANCHORS = {"aep.": {"archiepiscopus"}}


def markup(source, final, **earlier):
    """Mark up one text; `earlier` gives the stages before the final one."""
    stages = dict(earlier)
    stages["normalized"] = final
    segments, unplaced = mark_up(source, stages, ANCHORS, KNOWN)
    return render(segments), unplaced


class TestTokenSpans:
    def test_offsets(self):
        assert token_spans("in eccl.") == [("in", 0, 2), ("eccl.", 3, 8)]

    def test_shelfmark_is_glued_to_a_number(self):
        tokens = token_spans("V 314 236v.")
        assert is_shelfmark(tokens, 3)          # the v. of 236v.
        assert not is_shelfmark(tokens, 0)

    def test_a_separate_word_is_not_a_shelfmark(self):
        tokens = token_spans("in eccl. mai.")
        assert not is_shelfmark(tokens, 2)


class TestMarkUp:
    def test_a_plain_expansion(self):
        out, _ = markup("in eccl.", "in ecclesiae")
        assert out == ("in <choice><abbr>eccl.</abbr>"
                       '<expan resp="#step4">ecclesiae</expan></choice>')

    def test_a_word_that_was_never_abbreviated_is_not_marked(self):
        out, _ = markup("in ecclesia", "in ecclesia")
        assert out == "in ecclesia"

    def test_one_abbreviation_expanding_to_several_words(self):
        out, _ = markup("cum gr. exp.", "cum gratia expectativa")
        assert "<abbr>gr.</abbr>" in out and ">gratia<" in out
        assert "<abbr>exp.</abbr>" in out and ">expectativa<" in out

    def test_an_abbreviation_the_pipeline_left_standing(self):
        out, _ = markup("de etc. rapuerunt", "de etc. rapuerunt")
        assert out == "de <abbr>etc.</abbr> rapuerunt"

    def test_a_word_ending_a_sentence_is_not_an_abbreviation(self):
        out, _ = markup("divisionem fecerunt.", "divisionem fecerunt.")
        assert out == "divisionem fecerunt."

    def test_a_folio_mark_is_not_an_abbreviation(self):
        out, _ = markup("V 314 236v.", "V 314 236v.")
        assert out == "V 314 236v."

    def test_punctuation_the_expansion_adds_belongs_to_the_expansion(self):
        out, _ = markup("Albertus aep. Magdeburg",
                        "Albertus archiepiscopus, Magdeburg")
        assert ">archiepiscopus,<" in out
        assert out.count(",") == 1     # the comma is not also outside the choice

    def test_several_abbreviations_sharing_one_expansion_are_one_choice(self):
        out, _ = markup("de s.p.d. S", "de sineperdatum S")
        assert out.count("<choice>") == 1
        assert "<abbr>s.p.d.</abbr>" in out


class TestReadings:
    @pytest.mark.parametrize(
        "source, final",
        [
            ("in eccl. mai., domum", "in ecclesiae maiori, domum"),
            ("Albertus aep. etc. Magd", "Albertus archiepiscopus, prepositus et decanus Magd"),
            ("o. s. Ben. dioc.", "ordinis sancti Benedicti diocesis"),
            ("de etc. rapuerunt", "de etc. rapuerunt"),
            ("V 314 236v.", "V 314 236v."),
            ("de s.p.d. S", "de sineperdatum S"),
        ],
    )
    def test_both_readings_come_back_out(self, source, final):
        out, _ = markup(source, final)
        assert readings(out) == (source, final)

    def test_an_unresolved_abbreviation_is_in_both_readings(self):
        out, _ = markup("de etc. rapuerunt", "de etc. rapuerunt")
        abbreviated, expanded = readings(out)
        assert "etc." in abbreviated and "etc." in expanded

    def test_the_source_reading_keeps_the_original_spelling(self):
        out, _ = markup("eccl. par.", "ecclesia parochialis")
        assert readings(out)[0] == "eccl. par."

    def test_escaping_survives_the_round_trip(self):
        out, _ = markup("in <eccl.> & mai.", "in <ecclesia> & maior")
        assert "&lt;" in out and "&amp;" in out
        assert readings(out) == ("in <eccl.> & mai.", "in <ecclesia> & maior")


class TestAttribution:
    def test_the_step_that_expanded_it(self):
        out, _ = markup("in eccl.", "in ecclesia",
                        once="in ecclesia", twice="in ecclesia", thrice="in ecclesia")
        assert 'resp="#step1"' in out

    def test_a_later_step_that_changed_the_form_again(self):
        out, _ = markup("in eccl.", "in ecclesiae",
                        once="in ecclesia", twice="in ecclesia", thrice="in ecclesia")
        assert 'resp="#step1 #step4"' in out

    def test_an_abbreviation_an_early_step_could_not_expand(self):
        out, _ = markup("de conc.", "de concessio",
                        once="de conc.", twice="de concessio", thrice="de concessio")
        assert 'resp="#step2"' in out

    def test_attribute_ignores_stages_that_left_it_abbreviated(self):
        source, stages = "de conc.", {"once": "de conc.", "normalized": "de concessio"}
        tokens = token_spans(source)
        stage_tokens = {n: token_spans(t) for n, t in stages.items()}
        spans = {"once": [(0, 1), (1, 2)], "normalized": [(0, 1), (1, 2)]}
        assert attribute(1, "conc.", stages, stage_tokens, spans) == "#step4"


class TestSegment:
    def test_plain_text(self):
        assert Segment("in").plain

    def test_a_kept_abbreviation_is_not_plain(self):
        assert not Segment("etc.", kept=True).plain

    def test_a_choice_is_not_plain(self):
        assert not Segment("eccl.", "ecclesia").plain


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
