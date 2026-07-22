#!/usr/bin/env python3
"""
Test suite for the multiple-choice expansion step.

Covers:
- locating occurrences (word boundaries, optional spaces, overlap resolution)
- marking the text for the prompt
- parsing model responses (fences, invalid/missing/unknown choices)
- applying choices programmatically
"""

import pytest

from multiple_choice import (
    apply_choices,
    build_user_prompt,
    find_candidate_occurrences,
    mark_text,
    parse_choices,
)


class TestFindCandidateOccurrences:
    def test_simple_occurrences_numbered_left_to_right(self):
        text = "de conf. d. incorp."
        candidates = {"conf.": ["confirmare", "confirmatio"], "d.": ["dominus", "dictus"]}

        occs = find_candidate_occurrences(text, candidates)

        assert [(o.id, o.matched) for o in occs] == [(1, "conf."), (2, "d.")]
        assert text[occs[0].start : occs[0].end] == "conf."

    def test_word_boundary_no_match_inside_word(self):
        # `s.` must not match the end of `episcopus.` nor inside `Misnen.`
        text = "episcopus s. Misnen."
        candidates = {"s.": ["sanctus", "sub"]}

        occs = find_candidate_occurrences(text, candidates)

        assert len(occs) == 1
        assert (occs[0].start, occs[0].end) == (10, 12)

    def test_case_sensitive(self):
        text = "Cur. et cur."
        candidates = {"cur.": ["curia"]}

        occs = find_candidate_occurrences(text, candidates)

        assert len(occs) == 1
        assert occs[0].start == 8

    def test_multiword_wins_over_parts(self):
        text = "abb. et conv. mon."
        candidates = {
            "abb. et conv.": ["abbas et conventus"],
            "abb.": ["abbas", "abbatissa"],
            "conv.": ["conventus"],
            "mon.": ["monasterium"],
        }

        occs = find_candidate_occurrences(text, candidates)

        assert [o.matched for o in occs] == ["abb. et conv.", "mon."]

    def test_optional_space_variant_matches_and_deduplicates(self):
        # the text lacks the space, both the spaced key and its spacing variant
        # match the same span -> only one occurrence
        text = "abb.et conv."
        candidates = {"abb. et conv.": ["abbas et conventus"]}

        occs = find_candidate_occurrences(text, candidates)

        assert len(occs) == 1
        assert occs[0].matched == "abb.et conv."

    def test_repeated_abbreviation_gets_separate_ids(self):
        text = "conf. et conf."
        candidates = {"conf.": ["confirmare", "confirmatio"]}

        occs = find_candidate_occurrences(text, candidates)

        assert [o.id for o in occs] == [1, 2]


class TestMarkText:
    def test_marks_do_not_alter_rest_of_text(self):
        text = "de conf. d. incorp."
        candidates = {"conf.": ["confirmatio"], "d.": ["dominus"]}
        occs = find_candidate_occurrences(text, candidates)

        marked = mark_text(text, occs)

        assert marked == "de [[1|conf.]] [[2|d.]] incorp."

    def test_prompt_lists_all_occurrences(self):
        text = "conf. et conf."
        candidates = {"conf.": ["confirmare", "confirmatio"]}
        occs = find_candidate_occurrences(text, candidates)

        prompt = build_user_prompt(text, occs, candidates)

        assert "[[1]] `conf.`: `confirmare`, `confirmatio`" in prompt
        assert "[[2]] `conf.`: `confirmare`, `confirmatio`" in prompt


class TestParseChoices:
    def _setup(self):
        text = "de conf. d. incorp."
        candidates = {"conf.": ["confirmare", "confirmatio"], "d.": ["dominus", "dictus"]}
        occs = find_candidate_occurrences(text, candidates)
        return text, candidates, occs

    def test_valid_response(self):
        _, candidates, occs = self._setup()

        choices, errors = parse_choices(
            '{"1": "confirmatio", "2": "dominus"}', occs, candidates
        )

        assert choices == {1: "confirmatio", 2: "dominus"}
        assert errors == []

    def test_markdown_fences_and_prose_are_tolerated(self):
        _, candidates, occs = self._setup()

        content = 'Here you go:\n```json\n{"1": "confirmatio", "2": "dictus"}\n```'
        choices, errors = parse_choices(content, occs, candidates)

        assert choices == {1: "confirmatio", 2: "dictus"}
        assert errors == []

    def test_invalid_choice_is_reported_and_skipped(self):
        _, candidates, occs = self._setup()

        choices, errors = parse_choices(
            '{"1": "confirmatione", "2": "dominus"}', occs, candidates
        )

        assert choices == {2: "dominus"}
        assert len(errors) == 1
        assert "Invalid choice" in errors[0]["message"]

    def test_missing_choice_is_reported(self):
        _, candidates, occs = self._setup()

        choices, errors = parse_choices('{"1": "confirmatio"}', occs, candidates)

        assert choices == {1: "confirmatio"}
        assert len(errors) == 1
        assert "Missing choice" in errors[0]["message"]

    def test_unknown_id_is_reported(self):
        _, candidates, occs = self._setup()

        choices, errors = parse_choices(
            '{"1": "confirmatio", "2": "dominus", "9": "sanctus"}', occs, candidates
        )

        assert choices == {1: "confirmatio", 2: "dominus"}
        assert len(errors) == 1
        assert "Unknown id" in errors[0]["message"]

    def test_no_json_returns_none(self):
        _, candidates, occs = self._setup()

        choices, errors = parse_choices("I cannot help with that.", occs, candidates)

        assert choices is None
        assert len(errors) == 1


class TestApplyChoices:
    def test_substitution_leaves_rest_untouched(self):
        text = "de conf. d. incorp."
        candidates = {"conf.": ["confirmare", "confirmatio"], "d.": ["dominus", "dictus"]}
        occs = find_candidate_occurrences(text, candidates)

        result = apply_choices(text, occs, {1: "confirmatio", 2: "dominus"})

        assert result == "de confirmatio dominus incorp."

    def test_missing_choice_keeps_abbreviation(self):
        text = "de conf. d. incorp."
        candidates = {"conf.": ["confirmatio"], "d.": ["dominus"]}
        occs = find_candidate_occurrences(text, candidates)

        result = apply_choices(text, occs, {2: "dominus"})

        assert result == "de conf. dominus incorp."

    def test_trailing_punctuation_is_preserved(self):
        # `exec.:` -> the colon is not part of the match and must survive
        text = "exec.: abbas"
        candidates = {"exec.": ["executor", "executio"]}
        occs = find_candidate_occurrences(text, candidates)

        result = apply_choices(text, occs, {1: "executor"})

        assert result == "executor: abbas"

    def test_multiword_expansion(self):
        text = "abb. et conv. mon."
        candidates = {
            "abb. et conv.": ["abbas et conventus"],
            "mon.": ["monasterium"],
        }
        occs = find_candidate_occurrences(text, candidates)

        result = apply_choices(
            text, occs, {1: "abbas et conventus", 2: "monasterium"}
        )

        assert result == "abbas et conventus monasterium"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
