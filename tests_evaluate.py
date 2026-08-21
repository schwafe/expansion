#!/usr/bin/env python3
"""
Test suite for step 5 (measuring the expansion against the gold labels).

Covers:
- the orthographic key (the spellings the RG uses interchangeably)
- the stem-and-ending fallback for words the glossary has no morphology for
- the alignment: one-to-many expansions, multi-word abbreviations, an
  abbreviation the gold leaves standing, a passage the gold drops, and the
  ambiguous case that must be reported instead of scored
- the verdicts and the step attribution
- the candidate coverage: which errors the offered list could not have avoided
- the summary rates and the baseline diff
"""

import json

import pytest

from evaluate import (
    Occurrence,
    align,
    build_anchor_index,
    build_lemma_index,
    candidate_covers,
    candidate_summary,
    evaluate_vita,
    headline,
    inflectional_variants,
    load_candidates,
    orthographic_key,
    phrase_key,
    rates,
    render_baseline_diff,
    subalign,
    summarize,
    tokenize,
    verdict,
)

ENTRIES = [
    ("ecclesia", "ecclesi -e", "a"),
    ("ordo", "ordin -is", "kons."),
    ("annus", "ann -i", "o"),
    ("civitas", "civitat -is", "kons."),
    ("archiepiscopus", "archiepiscop -i", "o"),
    ("et cetera", "et; cetera", "-; -"),
    ("litterae", "?", "?"),  # unknown morphology
]


@pytest.fixture
def lemma_index():
    return build_lemma_index(ENTRIES)


class TestOrthographicKey:
    @pytest.mark.parametrize(
        "a, b",
        [
            ("ecclesiae", "ecclesie"),  # the RG writes ae and e
            ("opidum", "oppidum"),  # doubled consonants
            ("parrochialis", "parochialis"),
            ("Iohannes", "Johannes"),  # i/j
            ("uacante", "vacante"),  # u/v
            ("Ecclesia", "ecclesia."),  # case and trailing period
        ],
    )
    def test_variants_share_a_key(self, a, b):
        assert orthographic_key(a) == orthographic_key(b)

    def test_different_words_do_not(self):
        assert orthographic_key("ordo") != orthographic_key("obitus")

    def test_phrase_key_covers_every_word(self):
        assert phrase_key("ordinis sancti Benedicti") == phrase_key("ordinis sancti benedicti")


class TestInflectionalVariants:
    @pytest.mark.parametrize("a, b", [("nuntio", "nuntius"), ("misnensem", "misnensis")])
    def test_accepts_two_forms_of_one_word(self, a, b):
        assert inflectional_variants(orthographic_key(a), orthographic_key(b))

    @pytest.mark.parametrize(
        "a, b",
        [
            ("assignandi", "assignationis"),  # gerund vs. noun, not one word
            ("Terdonensis", "Terdonis"),  # two derivations from one place
            ("ordo", "obitus"),
        ],
    )
    def test_rejects_derivations_and_different_words(self, a, b):
        assert not inflectional_variants(orthographic_key(a), orthographic_key(b))


class TestAlign:
    def test_unchanged_words_map_one_to_one(self):
        source = tokenize("in eccl. maiori")
        target = tokenize("in ecclesia maiori")
        assert align(source, target) == [(0, 1), (1, 2), (2, 3)]

    def test_one_abbreviation_expanding_to_several_words(self):
        source = tokenize("m. evoc. can.")
        target = tokenize("mandatum evocandi canonicos")
        spans = align(source, target)
        assert [target[a:b] for a, b in spans] == [
            ["mandatum"], ["evocandi"], ["canonicos"]
        ]

    def test_multi_word_abbreviation_run(self):
        source = tokenize("o. s. Ben. Terdon. dioc.")
        target = tokenize("ordinis sancti Benedicti Terdonensis diocesis")
        spans = align(source, target)
        assert [" ".join(target[a:b]) for a, b in spans] == target

    def test_abbreviation_whose_expansion_does_not_continue_it(self):
        # aep. -> archiepiscopus is only known from the glossary, and the
        # unanchored etc. must take the rest instead of aep. swallowing it
        anchors = {"aep.": {"archiepiscopus"}}
        source = tokenize("Albertus aep. etc. Magdeburg")
        target = tokenize("Albertus archiepiscopus, prepositus, decanus et canonici Magdeburg")
        spans = align(source, target, anchors)
        assert " ".join(target[spans[1][0]:spans[1][1]]) == "archiepiscopus"
        assert " ".join(target[spans[2][0]:spans[2][1]]) == "prepositus decanus et canonici"

    def test_abbreviation_the_target_leaves_standing(self):
        source = tokenize("26 apr. 1394")
        target = tokenize("26 apr. 1394")
        assert align(source, target) == [(0, 1), (1, 2), (2, 3)]

    def test_dropped_passage_gives_an_empty_span(self):
        source = tokenize("conc. indulg. iubilei")
        target = tokenize("conc.")
        spans = align(source, target)
        assert spans[2] == (1, 1)

    def test_ambiguous_run_is_reported_not_scored(self):
        # neither source token can be anchored in the target
        assert subalign(["x.", "y."], ["alpha", "beta", "gamma"]) == [None, None]

    def test_single_replacement_always_aligns(self):
        assert subalign(["x."], ["alpha"]) == [(0, 1)]


class TestBuildAnchorIndex:
    def test_reads_the_glossary(self, tmp_path):
        path = tmp_path / "glossary.csv"
        path.write_text(
            "Abkürzung,Auflösung,Wortstamm,Deklination\n"
            "aep.,archiepiscopus,archiepiscop -i,o\n"
            "etc.,et cetera,et; cetera,-; -\n",
            encoding="utf-8",
        )
        index = build_anchor_index(path)
        assert "archiepiscopus" in index["aep."]
        assert "archiepiscopi" in index["aep."]  # inflected forms too
        assert "et" not in index.get("etc.", set())  # too short to anchor


class TestVerdict:
    def test_exact_and_orthographic(self, lemma_index):
        assert verdict("ecclesia", "ecclesia", lemma_index) == "exact"
        assert verdict("ecclesiae", "ecclesie", lemma_index) == "orthographic"
        assert verdict("oppidum", "opidum", lemma_index) == "orthographic"

    def test_wrong_form_from_the_paradigm(self, lemma_index):
        assert verdict("ordinis", "ordo", lemma_index) == "wrong_form"
        assert verdict("ecclesiam", "ecclesia", lemma_index) == "wrong_form"

    def test_wrong_form_from_the_fallback(self, lemma_index):
        assert verdict("Misnensem", "Misnensis", lemma_index) == "wrong_form?"

    def test_wrong_word(self, lemma_index):
        assert verdict("ordinis", "obitus", lemma_index) == "wrong_word"
        assert verdict("assignandi", "assignationis", lemma_index) == "wrong_word"

    def test_a_different_number_of_words_is_a_wrong_word(self, lemma_index):
        assert verdict("et capitulum", "capitulum", lemma_index) == "wrong_word"

    def test_unexpanded_and_unaligned(self, lemma_index):
        assert verdict("ecclesia", "eccl.", lemma_index) == "not_expanded"
        assert verdict("ecclesia", "", lemma_index) == "not_expanded"
        assert verdict("ecclesia", None, lemma_index) == "unaligned"


SOURCE = "conc. indulg. eccl. mai. 26 apr. 1394"
STAGES = {
    "once": "conc. indulg. ecclesia mai. 26 apr. 1394",
    "twice": "concessio indulgentia ecclesia maior 26 aprilis 1394",
    "thrice": "concessio indulgentia ecclesia maior 26 aprilis 1394",
    "normalized": "concessio indulgentie ecclesiae maiori 26 aprilis 1394",
}
GOLD = "concessio indulgentie ecclesie maiori 26 apr. 1394"


class TestEvaluateVita:
    @pytest.fixture
    def occurrences(self, lemma_index):
        return evaluate_vita(2, 370, SOURCE, GOLD, STAGES, lemma_index)

    def test_every_abbreviation_of_the_source_is_scored(self, occurrences):
        assert [o.abbreviation for o in occurrences] == [
            "conc.", "indulg.", "eccl.", "mai.", "apr."
        ]

    def test_the_stages_are_scored_separately(self, occurrences):
        ecclesia = next(o for o in occurrences if o.abbreviation == "eccl.")
        assert ecclesia.verdicts["once"] == "wrong_form"  # base form, gold inflected
        # gold ecclesie, normalized ecclesiae: the same form, the other spelling
        assert ecclesia.verdicts["normalized"] == "orthographic"

    def test_an_abbreviation_the_gold_keeps_has_no_label(self, occurrences):
        april = next(o for o in occurrences if o.abbreviation == "apr.")
        assert set(april.verdicts.values()) == {"no_gold_label"}

    def test_unexpanded_in_an_early_stage(self, occurrences):
        concessio = next(o for o in occurrences if o.abbreviation == "conc.")
        assert concessio.verdicts["once"] == "not_expanded"
        assert concessio.verdicts["twice"] == "exact"

    def test_attribution_names_the_step_that_expanded_it(self, occurrences):
        by_abbreviation = {o.abbreviation: o.step for o in occurrences}
        assert by_abbreviation["eccl."] == "step 4 (normalized)"  # step 1, refixed by 4
        assert by_abbreviation["conc."] == "step 2 (candidates)"
        assert by_abbreviation["apr."] == "step 2 (candidates)"


class TestSummary:
    def test_rates_ignore_the_unscoreable_verdicts(self):
        from collections import Counter

        summary = rates(Counter({
            "exact": 6, "orthographic": 1, "wrong_form": 2, "wrong_word": 1,
            "no_gold_label": 5, "unaligned": 3,
        }))
        assert summary["occurrences"] == 18
        assert summary["scoreable"] == 10
        assert summary["word_accuracy"] == pytest.approx(0.9)
        assert summary["form_accuracy"] == pytest.approx(0.7)
        assert summary["expanded"] == pytest.approx(1.0)

    def test_summarize_groups_by_abbreviation_and_step(self, lemma_index):
        occurrences = evaluate_vita(2, 370, SOURCE, GOLD, STAGES, lemma_index)
        summary = summarize(occurrences, list(STAGES), {"vitae_scored": 1})
        assert summary["final_stage"] == "normalized"
        assert summary["by_abbreviation"]["eccl."]["form_accuracy"] == pytest.approx(1.0)
        assert "step 2 (candidates)" in summary["by_step"]

    def test_baseline_diff_reports_the_change(self):
        current = {"normalized": {"word_accuracy": 0.95, "form_accuracy": 0.70,
                                  "expanded": 1.0, "scoreable": 100}}
        previous = {"normalized": {"word_accuracy": 0.93, "form_accuracy": 0.70,
                                   "expanded": 1.0, "scoreable": 100}}
        diff = render_baseline_diff(current, previous)
        assert "word accuracy +2.00pp" in diff
        assert "form accuracy +0.00pp" in diff

    def test_headline_is_stable_across_runs(self, lemma_index):
        occurrences = evaluate_vita(2, 370, SOURCE, GOLD, STAGES, lemma_index)
        summary = summarize(occurrences, list(STAGES), {})
        assert headline(summary) == headline(summary)


class TestCandidateCoverage:
    def test_a_candidate_covers_the_gold_word_in_any_form(self, lemma_index):
        # step 2 offers base forms, the gold is inflected: still the right word
        assert candidate_covers("ecclesiam", ["ordo", "ecclesia"], lemma_index)

    def test_a_candidate_covers_the_other_spelling(self, lemma_index):
        assert candidate_covers("ecclesiae", ["ecclesie"], lemma_index)

    def test_a_list_without_the_gold_word_covers_nothing(self, lemma_index):
        assert not candidate_covers("ordinis", ["ecclesia", "civitas"], lemma_index)

    def test_the_dump_is_read_per_vita(self, tmp_path):
        dump = tmp_path / "results.json"
        dump.write_text(json.dumps([
            {"twice_expanded_text": "text of 2/370", "candidates": {"d.": ["datum", "dictus"]}},
        ]), encoding="utf-8")
        offered = load_candidates(dump, "twice_expanded_text", {(2, 370): "text of 2/370"})
        assert offered == {(2, 370): {"d.": ["datum", "dictus"]}}

    def test_a_dump_of_an_earlier_run_is_dropped(self, tmp_path):
        """The text a dump records must be the text being scored."""
        dump = tmp_path / "results.json"
        dump.write_text(json.dumps([
            {"twice_expanded_text": "the old text", "candidates": {"d.": ["datum"]}},
        ]), encoding="utf-8")
        assert load_candidates(dump, "twice_expanded_text", {(2, 370): "the new text"}) == {}

    def test_a_missing_dump_is_not_an_error(self, tmp_path):
        assert load_candidates(tmp_path / "nothing.json", "twice_expanded_text", {}) == {}

    def test_the_summary_splits_the_errors_into_misses_and_bad_choices(self):
        def occurrence(gold, expansion, verdict_, covered):
            one = Occurrence(2, 370, "d.", gold, "")
            one.step = "step 2 (candidates)"
            one.stage_expansions["normalized"] = expansion
            one.verdicts["normalized"] = verdict_
            one.candidates["twice"] = ["datum", "dictus"]
            one.covered["twice"] = covered
            return one

        summary = candidate_summary([
            occurrence("datum", "datum", "exact", True),
            occurrence("dicta", "datum", "wrong_word", True),   # could have chosen it
            occurrence("dies", "datum", "wrong_word", False),   # not on the list
        ], "normalized")["step 2 (candidates)"]

        assert summary["expansions"] == 3
        assert summary["errors"] == 2
        assert summary["candidate_misses"] == 1
        assert summary["ceiling"] == pytest.approx(2 / 3)
        assert summary["choice_accuracy"] == pytest.approx(1 / 2)
        assert summary["worst"] == [("d.", 1)]

    def test_a_right_answer_outside_the_list_is_counted_as_such(self):
        """Step 3 may expand freely, so it can be right without a suggestion."""
        one = Occurrence(2, 370, "Terdon.", "Terdonensis", "")
        one.step = "step 3 (mined)"
        one.stage_expansions["normalized"] = "Terdonensis"
        one.verdicts["normalized"] = "exact"
        one.candidates["thrice"] = ["Terdonis"]
        one.covered["thrice"] = False

        summary = candidate_summary([one], "normalized")["step 3 (mined)"]
        assert summary["beyond"] == 1
        assert summary["candidate_misses"] == 0


class TestOccurrence:
    def test_defaults_are_independent(self):
        first, second = Occurrence(2, 1, "s.", "sancti", ""), Occurrence(2, 2, "s.", "sancti", "")
        first.verdicts["once"] = "exact"
        assert second.verdicts == {}
