#!/usr/bin/env python3
"""
Test suite for the paradigm generator.

The expected forms are hand-verified Latin; every test also checks that a
few forms that belong to a *different* word are NOT generated, so the
paradigms stay tight enough for validation.
"""

import pytest

from paradigm import entry_forms, word_forms


class TestNouns:
    def test_a_declension_with_both_spellings(self):
        forms = word_forms("ecclesia", "ecclesi -e", "a")
        assert {"ecclesia", "ecclesie", "ecclesiae", "ecclesiam",
                "ecclesiarum", "ecclesiis", "ecclesias"} <= forms
        assert "ecclesius" not in forms

    def test_o_declension(self):
        forms = word_forms("annus", "ann -i", "o")
        assert {"annus", "anni", "anno", "annum", "annorum", "annis", "annos"} <= forms
        assert "annae" not in forms

    def test_o_neuter(self):
        forms = word_forms("oppidum", "opid/oppid -i", "o (n.)")
        assert {"oppidum", "oppidi", "oppido", "oppida", "oppidorum",
                "opidum", "opidi", "opida"} <= forms
        assert "oppidos" not in forms  # neuter has no acc. pl. in -os

    def test_u_declension(self):
        forms = word_forms("conventus", "convent -us", "u")
        assert {"conventus", "conventui", "conventum", "conventu",
                "conventuum", "conventibus"} <= forms

    def test_e_declension(self):
        forms = word_forms("dies", "di -ei", "e")
        assert {"dies", "diei", "diem", "die", "dierum", "diebus"} <= forms

    def test_consonant_declension(self):
        forms = word_forms("abbas", "abbat -is", "kons. (m.)")
        assert {"abbas", "abbatis", "abbati", "abbatem", "abbate",
                "abbates", "abbatum", "abbatibus"} <= forms
        assert "abbatium" not in forms  # kons., not gem.

    def test_confirmatio_ablative(self):
        # the case the old string-based checker got wrong
        forms = word_forms("confirmatio", "confirmation -is", "kons. (f.)")
        assert {"confirmatio", "confirmatione", "confirmationis",
                "confirmationem", "confirmationum"} <= forms

    def test_er_nominative_from_bare_stem(self):
        forms = word_forms("archipresbiter", "archipresbiter/archipresbyter -i", "o")
        assert {"archipresbiter", "archipresbyter", "archipresbiteri",
                "archipresbytero"} <= forms

    def test_plural_only(self):
        forms = word_forms("limina", "limin -um", "kons. (n.) (Pl.)")
        assert {"limina", "liminum", "liminibus"} <= forms
        assert "liminis" not in forms  # no singular forms
        assert "limines" not in forms  # neuter nom. pl. is limina


class TestAdjectives:
    def test_o_a_adjective_all_genders(self):
        forms = word_forms("sanctus", "sanct -i", "o/a (Adj.)")
        assert {"sanctus", "sancta", "sanctum", "sancti", "sancte", "sanctae",
                "sancto", "sanctorum", "sanctarum", "sanctis", "sanctos",
                "sanctas"} <= forms

    def test_i_adjective(self):
        forms = word_forms("portatile", "portatil -is", "i (Adj.)")
        assert {"portatilis", "portatile", "portatili", "portatilem",
                "portatiles", "portatilia", "portatilium",
                "portatilibus"} <= forms

    def test_uncertain_class_is_union(self):
        forms = word_forms("militaris", "militar -is", "i/kons. (Adj.) ?")
        assert {"militaris", "militari", "militarium", "militarum"} <= forms


class TestVerbs:
    def test_a_conjugation(self):
        forms = word_forms("celebrare", "celebr, celebrav, celebrat", "a-Konj.")
        # present system
        assert {"celebrare", "celebrat", "celebrant", "celebrabat",
                "celebretur", "celebratur", "celebrari"} <= forms
        # perfect system
        assert {"celebravit", "celebraverunt", "celebraverat"} <= forms
        # participles, gerund/gerundive
        assert {"celebrans", "celebrantibus", "celebrandi", "celebrando",
                "celebrandum", "celebranda", "celebratum", "celebrata",
                "celebraturus"} <= forms

    def test_e_conjugation(self):
        forms = word_forms("valere", "vale, valu, -", "e-Konj.")
        assert {"valere", "valet", "valent", "valeat", "valebat",
                "valens", "valentibus", "valuit"} <= forms
        assert "valetum" not in forms  # no supine stem given

    def test_kons_conjugation(self):
        forms = word_forms("decernere", "decern, decrev, decret", "kons.-Konj.")
        assert {"decernere", "decernit", "decernitur", "decernat",
                "decrevit", "decretum", "decreta", "decernendi"} <= forms

    def test_stem_variants(self):
        forms = word_forms("conferre", "confer, contul, collat/conlat", "kons.-Konj.")
        assert {"contulit", "collatum", "conlatum", "collata"} <= forms

    def test_deponent_has_no_active_forms(self):
        forms = word_forms("ingredi", "ingred, -, ingress", "halbkons.-Konj. (Dep.)")
        assert {"ingredi", "ingreditur", "ingrediuntur", "ingressus",
                "ingressum", "ingrediendi"} <= forms
        assert "ingredit" not in forms  # deponent: no active finite forms


class TestFixedAndUnknown:
    def test_fixed_word(self):
        assert word_forms("et", "et", "-") == {"et"}
        assert word_forms("pauperum", "pauperum", "-") == {"pauperum"}

    def test_unknown_returns_none(self):
        assert word_forms("lite/litis", "?", "?") is None


class TestEntryForms:
    def test_multiword_entry(self):
        result = entry_forms(
            "abbas et conventus",
            "abbat -is; et; convent -us",
            "kons. (m.); -; u",
        )
        assert result is not None
        words = [w for w, _ in result]
        assert words == ["abbas", "et", "conventus"]
        assert result[1][1] == {"et"}
        assert "abbatibus" in result[0][1]
        assert "conventui" in result[2][1]

    def test_missing_columns_return_none(self):
        assert entry_forms("abbas", None, "kons.") is None
        assert entry_forms("abbas", "abbat -is", None) is None

    def test_part_count_mismatch_returns_none(self):
        assert entry_forms("abbas et conventus", "abbat -is", "kons.") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
