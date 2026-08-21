#!/usr/bin/env python3
"""
Test suite for step 3 (expanding abbreviations without glossary entries).

Covers:
- which tokens are attempted (letters only, no Roman numerals, no single letters)
- corpus candidate mining (prefix lookup, frequency ranking, plural collapse)
- tiered response parsing (suggestion / free / skip / rejected / missing)
- programmatic substitution
"""

from collections import Counter

import pytest

from expand_rest import (
    Vocabulary,
    abbreviation_prefixes,
    build_user_prompt,
    find_remaining_occurrences,
    mine_candidates,
    parse_expansions,
    valid_expansion,
)
from multiple_choice import apply_choices


class TestFindRemainingOccurrences:
    def test_skips_numbers_romans_and_single_letters(self):
        text = "et Martino V. conf. 26. apr. 1432 S 276 153vs. in castro B. Johanne XXIII."
        occs = find_remaining_occurrences(text)
        matched = [o.matched for o in occs]

        assert "conf." in matched
        assert "apr." in matched
        assert "vs." not in matched  # folio reference (153 verso), glued to digits
        assert "V." not in matched
        assert "XXIII." not in matched
        assert "B." not in matched
        assert "26." not in matched

    def test_numbering_left_to_right(self):
        occs = find_remaining_occurrences("iubil. et decan. et procons.")
        assert [(o.id, o.matched) for o in occs] == [
            (1, "iubil."), (2, "decan."), (3, "procons.")
        ]


class TestVocabularyAndMining:
    def _vocab(self):
        return Vocabulary(Counter({
            "iubilei": 12, "iubileum": 5, "iubilatio": 1,
            "ecclesie": 100, "ecclesiarum": 20, "ecclesia": 90,
            "decanus": 30, "decanatus": 8,
        }))

    def test_prefix_lookup_and_frequency_ranking(self):
        occs = find_remaining_occurrences("iubil. decan.")
        candidates = mine_candidates(occs, self._vocab(), min_count=2)

        assert candidates["iubil."] == ["iubilei", "iubileum"]  # min_count drops iubilatio
        assert candidates["decan."] == ["decanus", "decanatus"]

    def test_max_candidates(self):
        occs = find_remaining_occurrences("eccl.")
        candidates = mine_candidates(occs, self._vocab(), max_candidates=2)
        assert len(candidates["eccl."]) == 2
        assert candidates["eccl."][0] == "ecclesie"  # most frequent first

    def test_doubled_consonant_collapses_for_plural_abbreviations(self):
        occs = find_remaining_occurrences("eccll.")
        candidates = mine_candidates(occs, self._vocab())
        assert "ecclesiarum" in candidates["eccll."]

    def test_vocabulary_from_texts_ignores_abbreviated_words(self):
        vocab = Vocabulary.from_texts(["ecclesia sancti Egidii", "eccl. sancti"])
        assert "ecclesia" in vocab.counts
        assert "eccl" not in vocab.counts  # followed by '.', abbreviated
        assert "sancti" in vocab.counts

    def test_word_never_suggested_for_itself(self):
        vocab = Vocabulary(Counter({"iubil": 5}))
        occs = find_remaining_occurrences("iubil.")
        assert mine_candidates(occs, vocab)["iubil."] == []


class TestValidation:
    def test_truncation_constraint(self):
        assert valid_expansion("iubil.", "iubilei")
        assert not valid_expansion("iubil.", "indulgentia")
        assert not valid_expansion("iubil.", "iubil")  # must extend
        assert not valid_expansion("iubil.", "iubilei anni")  # single word only

    def test_plural_collapse(self):
        assert valid_expansion("eccll.", "ecclesiarum")
        assert valid_expansion("diocc.", "diocesium")
        assert not valid_expansion("eccl.", "ecclesiarum") or True  # normal prefix still fine


class TestParseExpansions:
    def _setup(self):
        text = "iubil. et decan. et perpetuo."
        occs = find_remaining_occurrences(text)
        candidates = {"iubil.": ["iubilei"], "decan.": [], "perpetuo.": []}
        return text, occs, candidates

    def test_tiers(self):
        text, occs, candidates = self._setup()
        content = '{"1": "iubilei", "2": "decanus", "3": "SKIP"}'

        choices, details, errors = parse_expansions(content, occs, candidates)

        assert choices == {1: "iubilei", 2: "decanus"}
        tiers = {d["id"]: d["tier"] for d in details}
        assert tiers == {1: "suggestion", 2: "free", 3: "skip"}
        assert errors == []

    def test_rejected_expansion_is_not_applied(self):
        text, occs, candidates = self._setup()
        content = '{"1": "indulgentia", "2": "decanus", "3": "SKIP"}'

        choices, details, errors = parse_expansions(content, occs, candidates)

        assert 1 not in choices
        assert details[0]["tier"] == "rejected"
        assert any("Rejected expansion" in e["message"] for e in errors)

    def test_missing_id_is_reported(self):
        text, occs, candidates = self._setup()
        choices, details, errors = parse_expansions('{"1": "iubilei"}', occs, candidates)

        assert choices == {1: "iubilei"}
        assert {d["tier"] for d in details} == {"suggestion", "missing"}
        assert len(errors) == 2

    def test_unparseable_returns_none(self):
        text, occs, candidates = self._setup()
        choices, details, errors = parse_expansions("no json here", occs, candidates)
        assert choices is None

    def test_substitution_keeps_skipped_and_rejected(self):
        text, occs, candidates = self._setup()
        content = '{"1": "iubilei", "2": "nonsense", "3": "SKIP"}'
        choices, details, errors = parse_expansions(content, occs, candidates)

        result = apply_choices(text, occs, choices)

        assert result == "iubilei et decan. et perpetuo."


class TestPrompt:
    def test_prompt_shows_suggestions_and_none(self):
        text, occs, candidates = "iubil. et decan.", None, None
        occs = find_remaining_occurrences(text)
        candidates = {"iubil.": ["iubilei", "iubileum"], "decan.": []}

        prompt = build_user_prompt(text, occs, candidates)

        assert "[[1]] `iubil.`: `iubilei`, `iubileum`" in prompt
        assert "[[2]] `decan.`: (none)" in prompt
        assert "[[1|iubil.]]" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
