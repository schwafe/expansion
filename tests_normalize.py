#!/usr/bin/env python3
"""
Test suite for step 4 (normalizing the grammar of the expanded text).

Covers:
- lexicon building from glossary morphology (fixed/unknown words excluded,
  capitalized variants, diocese adjectives)
- which tokens are marked (base forms only, no unexpanded abbreviations)
- frequency ranking of the paradigm forms
- tiered response parsing (changed / kept / rejected / missing)
- programmatic substitution
"""

from collections import Counter

import pytest

from multiple_choice import apply_choices
from normalize import (
    build_lexicon,
    build_user_prompt,
    diocese_entries,
    find_lexicon_occurrences,
    inserted_spans,
    parse_forms,
    ranked_forms,
)

ENTRIES = [
    ("annus", "ann -i", "o"),
    ("ecclesia", "ecclesi -e", "a"),
    ("et", "et", "-"),  # fixed word, single form
    ("gratia expectativa", "grati -e; expectativ -e", "a; o/a (Adj.)"),
    ("litterae", "?", "?"),  # unknown morphology
    (None, None, None),  # unusable row
]


@pytest.fixture
def lexicon():
    return build_lexicon(ENTRIES + diocese_entries(["Bremensis", "Tridentinus"]))


class TestBuildLexicon:
    def test_paradigms_and_exclusions(self, lexicon):
        assert {"annus", "anni", "anno", "annis", "annorum"} <= lexicon["annus"]
        assert "et" not in lexicon  # single form, nothing to choose
        assert "litterae" not in lexicon  # unknown morphology

    def test_multi_word_entries_decompose(self, lexicon):
        assert "gratia" in lexicon
        assert "expectativa" in lexicon
        assert "expectativarum" in lexicon["expectativa"]

    def test_capitalized_variants(self, lexicon):
        assert "Ecclesia" in lexicon
        assert "Ecclesiarum" in lexicon["Ecclesia"]

    def test_diocese_adjectives(self, lexicon):
        assert "Bremensi" in lexicon["Bremensis"]
        assert "Bremensium" in lexicon["Bremensis"]
        assert "Tridentini" in lexicon["Tridentinus"]

    def test_base_form_always_included(self, lexicon):
        for word, forms in lexicon.items():
            assert word in forms


class TestFindLexiconOccurrences:
    def test_marks_base_forms_only(self, lexicon):
        text = "de 7 annus et ecclesia sancti Egidii Bremensis. anno domini"
        occs = find_lexicon_occurrences(text, lexicon)
        matched = [o.matched for o in occs]

        assert "annus" in matched
        assert "ecclesia" in matched
        assert "Bremensis" not in matched  # followed by '.', still abbreviated
        assert "anno" not in matched  # inflected original word, not a base form
        assert "et" not in matched

    def test_capitalized_occurrence(self, lexicon):
        occs = find_lexicon_occurrences("Ecclesia sancti Blasii", lexicon)
        assert [o.matched for o in occs] == ["Ecclesia"]

    def test_numbering_left_to_right(self, lexicon):
        occs = find_lexicon_occurrences("annus et gratia et ecclesia", lexicon)
        assert [(o.id, o.matched) for o in occs] == [
            (1, "annus"), (2, "gratia"), (3, "ecclesia")
        ]


class TestInsertedSpans:
    def test_inserted_words_only(self, lexicon):
        original = "de 7 a. et ecclesia sancti Egidii"
        expanded = "de 7 annus et ecclesia sancti Egidii"

        spans = inserted_spans(original, expanded)

        assert [expanded[s:e] for s, e in spans] == ["annus"]
        occs = find_lexicon_occurrences(expanded, lexicon, spans)
        # 'ecclesia' is an original word and must not be marked
        assert [o.matched for o in occs] == ["annus"]

    def test_multi_word_expansion(self):
        original = "cum gr. exp. concessa"
        expanded = "cum gratia expectativa concessa"

        spans = inserted_spans(original, expanded)

        assert [expanded[s:e] for s, e in spans] == ["gratia", "expectativa"]

    def test_kept_abbreviation_is_not_an_insertion(self, lexicon):
        original = "annus Bremen. et eccl. domini"
        expanded = "annus Bremen. et ecclesia domini"

        spans = inserted_spans(original, expanded)

        assert [expanded[s:e] for s, e in spans] == ["ecclesia"]
        # ... and the original 'annus' stays unmarked despite being a base form
        occs = find_lexicon_occurrences(expanded, lexicon, spans)
        assert [o.matched for o in occs] == ["ecclesia"]

    def test_consecutive_abbreviations(self):
        original = "in castro B. eccl. par. domini"
        expanded = "in castro B. ecclesia parochialis domini"

        spans = inserted_spans(original, expanded)

        assert [expanded[s:e] for s, e in spans] == ["ecclesia", "parochialis"]

    def test_nothing_expanded(self):
        text = "de conservatione 30. iunii 1435"
        assert inserted_spans(text, text) == []

    def test_corrupted_original_word_fails_alignment(self):
        # a full-text rewrite corrupted a word it should not have touched
        original = "in castro Halberstad. prope Woden flumen"
        expanded = "in castro Halberstadensis prope Weden flumen"

        assert inserted_spans(original, expanded) is None

    def test_dropped_original_word_fails_alignment(self):
        original = "ecclesia sancti Egidii Beati"
        expanded = "ecclesia sancti Egidii"

        assert inserted_spans(original, expanded) is None


class TestRankedForms:
    def test_frequency_ranking(self, lexicon):
        class FakeVocabulary:
            counts = Counter({"anno": 100, "annis": 50, "annus": 10})

        candidates = ranked_forms(lexicon, FakeVocabulary())
        assert candidates["annus"][:3] == ["anno", "annis", "annus"]

    def test_without_vocabulary_alphabetical(self, lexicon):
        candidates = ranked_forms(lexicon)
        assert candidates["annus"] == sorted(lexicon["annus"])


class TestParseForms:
    def _setup(self, lexicon):
        text = "de 7 annus in ecclesia"
        occs = find_lexicon_occurrences(text, lexicon)
        candidates = ranked_forms(lexicon)
        return text, occs, candidates

    def test_tiers(self, lexicon):
        text, occs, candidates = self._setup(lexicon)
        content = '{"1": "annis", "2": "ecclesia"}'

        choices, details, errors = parse_forms(content, occs, candidates)

        assert choices == {1: "annis"}  # kept forms need no substitution
        tiers = {d["id"]: d["tier"] for d in details}
        assert tiers == {1: "changed", 2: "kept"}
        assert errors == []

    def test_rejected_form_is_not_applied(self, lexicon):
        text, occs, candidates = self._setup(lexicon)
        content = '{"1": "ecclesiam", "2": "ecclesia"}'  # form of the wrong word

        choices, details, errors = parse_forms(content, occs, candidates)

        assert 1 not in choices
        assert details[0]["tier"] == "rejected"
        assert any("Rejected form" in e["message"] for e in errors)

    def test_missing_and_unknown_ids_are_reported(self, lexicon):
        text, occs, candidates = self._setup(lexicon)
        choices, details, errors = parse_forms('{"1": "annis", "9": "x"}', occs, candidates)

        assert choices == {1: "annis"}
        assert {d["tier"] for d in details} == {"changed", "missing"}
        assert len(errors) == 2

    def test_unparseable_returns_none(self, lexicon):
        text, occs, candidates = self._setup(lexicon)
        choices, details, errors = parse_forms("no json here", occs, candidates)
        assert choices is None

    def test_substitution(self, lexicon):
        text, occs, candidates = self._setup(lexicon)
        content = '{"1": "annis", "2": "ecclesia"}'
        choices, details, errors = parse_forms(content, occs, candidates)

        assert apply_choices(text, occs, choices) == "de 7 annis in ecclesia"


class TestPrompt:
    def test_prompt_shows_forms(self, lexicon):
        text = "de 7 annus"
        occs = find_lexicon_occurrences(text, lexicon)
        candidates = ranked_forms(lexicon)

        prompt = build_user_prompt(text, occs, candidates)

        assert "[[1|annus]]" in prompt
        assert "- [[1]] `annus`: " in prompt
        assert "`annis`" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
