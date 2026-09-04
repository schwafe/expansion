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
- which files a run is scored from, and what the report says produced them
"""

import json

import pytest

import evaluate
import runs
from evaluate import (
    Occurrence,
    align,
    candidate_dumps,
    describe_settings,
    produced_by,
    step_section,
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


class TestStagesOfARun:
    """Which files are scored comes from the run's manifest, not a constant."""

    @pytest.fixture(autouse=True)
    def a_temporary_runs_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(runs, "RUNS_DIR", tmp_path / "runs")
        monkeypatch.setattr(runs, "STEP1", tmp_path / "step1.csv")
        runs.STEP1.write_text("volume,nr_RG\n", encoding="utf-8")

    def produce(self, run, step, model="a-model", dump=True, parent=None):
        source, inherited = runs.resolve_input(run, step, parent)
        runs.record(run, step, inherited, model=model, thinking=None, reasoning_effort=None,
                    prompt_sha1="abc", input=str(source),
                    output=str(runs.output_path(run, step)),
                    dump=str(runs.dump_path(run, step)) if dump else None,
                    vitae=1, written="2026-08-28T00:00:00+00:00")

    def test_the_stages_are_the_steps_the_run_reached(self):
        self.produce("gemma", 2)
        self.produce("gemma", 3)
        assert [name for name, _, _ in evaluate.stages("gemma")] == [
            "source", "once", "twice", "thrice"
        ]

    def test_a_stage_points_at_the_run_that_produced_it(self):
        self.produce("gemma", 2)
        self.produce("gemma", 3)
        self.produce("qwen-nothink", 4, model="qwen3.8-27b", parent="gemma")
        paths = {name: path for name, _, path in evaluate.stages("qwen-nothink")}
        assert paths["thrice"] == runs.output_path("gemma", 3)
        assert paths["normalized"] == runs.output_path("qwen-nothink", 4)

    def test_the_candidate_dumps_follow_the_steps_that_wrote_them(self):
        self.produce("gemma", 2)
        self.produce("gemma", 3)
        self.produce("qwen-nothink", 4, model="qwen3.8-27b", parent="gemma")
        dumps = {stage: path for stage, path, _ in candidate_dumps("qwen-nothink")}
        assert dumps == {"twice": runs.dump_path("gemma", 2),
                         "thrice": runs.dump_path("gemma", 3)}

    def test_a_step_without_a_dump_is_left_out_rather_than_guessed(self):
        self.produce("gemma", 2, dump=False)
        assert candidate_dumps("gemma") == []


class TestProducedBy:
    """The report says which model did which step, through however many runs."""

    def info(self, steps):
        return {"produced_by": steps}

    def test_step_one_is_named_as_the_rule_it_is(self):
        rendered = "\n".join(produced_by(self.info({"1": {"run": None, "model": None}})))
        assert "rule" in rendered and "expand_simple" in rendered

    def test_a_step_carries_its_model_settings_and_run(self):
        rendered = "\n".join(produced_by(self.info({"4": {
            "run": "qwen3.8-27b-nothink", "model": "qwen3.8-27b", "thinking": False,
            "written": "2026-08-28T00:00:00+00:00"}})))
        assert "`qwen3.8-27b`" in rendered and "off" in rendered
        assert "`qwen3.8-27b-nothink`" in rendered

    def test_a_step_from_before_the_dumps_recorded_a_date_says_so(self):
        rendered = "\n".join(produced_by(self.info({"3": {
            "run": "gemma", "model": "gemma-4-31b-it", "thinking": None, "written": None}})))
        assert "unrecorded" in rendered


class TestStepSections:
    """
    Every run at the same step, so the models of one step can be compared.

    The table above them scores each run where its chain has got to, which
    makes a run that has been through step 4 look better at step 2 than one
    that stopped there.
    """

    @pytest.fixture(autouse=True)
    def a_temporary_runs_dir(self, tmp_path, monkeypatch):
        """The chain behind a step is read from the manifests, so keep them here."""
        monkeypatch.setattr(runs, "RUNS_DIR", tmp_path / "runs")
        monkeypatch.setattr(runs, "STEP1", tmp_path / "step1.csv")
        runs.STEP1.write_text("volume,nr_RG\n", encoding="utf-8")

    def scored(self, name, chain, **stages):
        """One run: what its stages scored, and which model did which step."""
        summary = {"stages": {stage: {"word_accuracy": word, "form_accuracy": form,
                                      "scoreable": 100}
                              for stage, (word, form) in stages.items()}}
        steps = {number: {"run": produced, "model": model, "thinking": False,
                          "reasoning_effort": None,
                          "output": f"data/runs/{produced}/step{number}.csv"}
                 for number, (produced, model) in chain.items()}
        return (name, summary, steps)

    def two_runs_through_step_2(self):
        return [
            self.scored("gemma", {2: ("gemma", "gemma-4-31b-it")},
                        once=(0.6, 0.3), twice=(0.89, 0.44)),
            self.scored("qwen-nothink", {2: ("qwen-nothink", "qwen3.8-27b")},
                        once=(0.6, 0.3), twice=(0.87, 0.43)),
        ]

    def test_the_best_at_this_step_comes_first(self):
        rendered = "\n".join(step_section(2, self.two_runs_through_step_2()))
        assert rendered.index("gemma-4-31b-it") < rendered.index("qwen3.8-27b")

    def test_what_a_step_gained_is_measured_against_the_stage_before_it(self):
        # the chains differ from step 2 on, so what a later step is worth is
        # not its own number but the rise over what it was handed
        rendered = "\n".join(step_section(2, self.two_runs_through_step_2()))
        assert "+29.0pp" in rendered  # 0.89 over 0.60
        assert "+27.0pp" in rendered

    def test_a_run_that_has_not_reached_the_step_is_left_out(self):
        rendered = "\n".join(step_section(3, self.two_runs_through_step_2()))
        assert rendered == ""

    def test_step_4_is_read_by_the_accuracy_it_can_move(self):
        # word accuracy is step 4's to keep, not to raise: it only inflects
        scored = [
            self.scored("careful", {2: ("careful", "a-model"), 3: ("careful", "a-model"),
                                    4: ("careful", "a-model")},
                        thrice=(0.90, 0.40), normalized=(0.90, 0.65)),
            self.scored("wordy", {2: ("wordy", "b-model"), 3: ("wordy", "b-model"),
                                  4: ("wordy", "b-model")},
                        thrice=(0.95, 0.40), normalized=(0.95, 0.55)),
        ]
        rendered = "\n".join(step_section(4, scored))
        assert rendered.index("a-model") < rendered.index("b-model")

    def test_a_step_two_runs_share_is_one_row_under_the_run_that_made_it(self):
        # --from means the same file, and so the same score, twice
        scored = [
            self.scored("gemma", {2: ("gemma", "gemma-4-31b-it")},
                        once=(0.6, 0.3), twice=(0.89, 0.44)),
            self.scored("qwen-on-gemma", {2: ("gemma", "gemma-4-31b-it"),
                                          3: ("qwen-on-gemma", "qwen3.8-27b")},
                        once=(0.6, 0.3), twice=(0.89, 0.44), thrice=(0.92, 0.46)),
        ]
        rendered = "\n".join(step_section(2, scored))
        assert rendered.count("gemma-4-31b-it") == 1
        assert "qwen-on-gemma" not in rendered

    def record(self, run, step, model, parent=None):
        """A step's worth of manifest, so the chain behind it can be followed."""
        source, inherited = runs.resolve_input(run, step, parent)
        runs.record(run, step, inherited, model=model, thinking=False,
                    reasoning_effort=None, input=str(source),
                    output=str(runs.output_path(run, step)))

    def a_run_that_took_its_step_2_from_another(self):
        """
        qwen ran step 2 itself, then ran step 3 on gemma's step 2 instead.

        Its manifest holds both, so the step numbers alone would credit step 3
        with the step 2 it did not read.
        """
        self.record("gemma", 2, "gemma-4-31b-it")
        self.record("qwen-nothink", 2, "qwen3.8-27b")
        self.record("qwen-nothink", 3, "qwen3.8-27b", parent="gemma")
        return [
            self.as_recorded("gemma", once=(0.60, 0.30), twice=(0.89, 0.44)),
            self.as_recorded("qwen-nothink",
                             once=(0.60, 0.30), twice=(0.87, 0.43), thrice=(0.92, 0.46)),
        ]

    def as_recorded(self, name, **stages):
        """One scored run, its chain read back from the manifest it wrote."""
        summary = {"stages": {stage: {"word_accuracy": word, "form_accuracy": form,
                                      "scoreable": 100}
                              for stage, (word, form) in stages.items()}}
        return (name, summary, dict(runs.chain(name)))

    def test_a_step_names_the_models_behind_the_file_it_read(self):
        rendered = "\n".join(step_section(3, self.a_run_that_took_its_step_2_from_another()))
        row = [line for line in rendered.splitlines() if "qwen3.8-27b" in line][0]
        assert "gemma-4-31b-it" in row  # step 2 was gemma's, not this run's own

    def test_what_a_step_gained_is_measured_against_the_file_it_read(self):
        rendered = "\n".join(step_section(3, self.a_run_that_took_its_step_2_from_another()))
        assert "+3.0pp" in rendered  # 0.92 over gemma's 0.89, not over its own 0.87
        assert "+5.0pp" not in rendered

    def test_the_run_s_own_step_is_still_scored_at_its_own_step(self):
        # it is a real file and a real model at step 2, whatever step 3 read
        rendered = "\n".join(step_section(2, self.a_run_that_took_its_step_2_from_another()))
        assert "qwen3.8-27b" in rendered and "+27.0pp" in rendered


class TestDescribeSettings:
    def test_the_default_is_named_rather_than_left_blank(self):
        assert describe_settings({"thinking": None, "reasoning_effort": None}) == "default"

    def test_the_switch_is_reported_either_way(self):
        assert describe_settings({"thinking": False}) == "off"
        assert describe_settings({"thinking": True}) == "on"

    def test_a_level_is_reported_instead_of_the_switch_it_implies(self):
        assert describe_settings({"thinking": True, "reasoning_effort": "low"}) == "effort low"
