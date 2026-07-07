#!/usr/bin/env python3
"""
Paradigm generation from the cleaned Wortstamm/Deklination columns
(format documented in clean_morphology.py and the README).

For every word of an Auflösung the generator produces the set of surface
forms that an inflected expansion may take in the RG texts:

- nouns: all cases, singular and plural (plural only for `(Pl.)` entries)
- adjectives/participles: all cases, numbers, and genders
- verbs: present system (indicative, subjunctive, active and passive,
  imperfect, future), infinitives, imperatives, present participle,
  gerund/gerundive, the perfect system (from the perfect stem), and the
  participles/supine built on the supine stem
- fixed words (Deklination `-`): only the word itself

The dictionary form (the Auflösung word) is always part of its own paradigm,
which also covers nominatives that cannot be derived from the stem (abbas,
prothomartir, ...). Forms with `ae` are additionally generated in the RG's
`e` spelling and vice versa.

Main entry point: `entry_forms(aufloesung, wortstamm, deklination)`.
"""

import re

from clean_morphology import aufloesung_words

# --------------------------------------------------------------------------
# noun and adjective endings (attached to the stem)
# --------------------------------------------------------------------------

NOUN_ENDINGS: dict[str, tuple[set[str], set[str]]] = {
    # class: (singular endings, plural endings)
    "a": ({"a", "ae", "am"}, {"ae", "arum", "is", "as"}),
    "o": ({"us", "i", "o", "um", "e"}, {"i", "orum", "is", "os"}),
    "o_n": ({"um", "i", "o"}, {"a", "orum", "is"}),
    "u": ({"us", "ui", "um", "u"}, {"us", "uum", "ibus"}),
    "e": ({"es", "ei", "em", "e"}, {"es", "erum", "ebus"}),
    "kons": ({"is", "i", "em", "e"}, {"es", "um", "ibus"}),
    "kons_n": ({"is", "i", "e"}, {"a", "um", "ibus"}),
    "gem": ({"is", "i", "em", "e"}, {"es", "ium", "ibus"}),
    "gem_n": ({"is", "i", "e"}, {"ia", "ium", "ibus"}),
    "i": ({"is", "i", "em", "im", "e"}, {"es", "ium", "ibus", "is"}),
    "i_n": ({"is", "i"}, {"ia", "ium", "ibus"}),
}

ADJ_ENDINGS: dict[str, tuple[set[str], set[str]]] = {
    # all genders combined
    "o/a": (
        NOUN_ENDINGS["o"][0] | NOUN_ENDINGS["a"][0] | NOUN_ENDINGS["o_n"][0],
        NOUN_ENDINGS["o"][1] | NOUN_ENDINGS["a"][1] | NOUN_ENDINGS["o_n"][1],
    ),
    "i": ({"is", "i", "em", "e"}, {"es", "ia", "ium", "ibus"}),
    "kons": ({"is", "i", "em", "e"}, {"es", "a", "um", "ibus"}),
}

# --------------------------------------------------------------------------
# verb endings (attached to the present stem), by conjugation
# --------------------------------------------------------------------------


def _persons(base: str, first: str, last: str) -> list[str]:
    return [first, base + "s", base + "t", base + "mus", base + "tis", last]


def _persons_passive(base: str, first: str, last: str) -> list[str]:
    return [first, base + "ris", base + "tur", base + "mur", base + "mini", last]


def _conjugation_suffixes() -> dict[str, set[str]]:
    conj: dict[str, list[str]] = {}

    conj["a"] = (
        _persons("a", "o", "ant")  # present active
        + _persons("aba", "abam", "abant")  # imperfect active
        + _persons("abi", "abo", "abunt")  # future active
        + _persons("e", "em", "ent")  # present subjunctive
        + _persons("are", "arem", "arent")  # imperfect subjunctive
        + ["are", "a", "ate"]  # infinitive, imperatives
        + _persons_passive("a", "or", "antur")
        + _persons_passive("aba", "abar", "abantur")
        + ["abor", "aberis", "abitur", "abimur", "abimini", "abuntur"]
        + _persons_passive("e", "er", "entur")
        + _persons_passive("are", "arer", "arentur")
        + ["ari"]
    )
    conj["e"] = (  # attached to a present stem that ends in -e (vale-)
        _persons("", "o", "nt")
        + _persons("ba", "bam", "bant")
        + _persons("bi", "bo", "bunt")
        + _persons("a", "am", "ant")
        + _persons("re", "rem", "rent")
        + ["re", "", "te"]
        + _persons_passive("", "or", "ntur")
        + _persons_passive("ba", "bar", "bantur")
        + ["bor", "beris", "bitur", "bimur", "bimini", "buntur"]
        + _persons_passive("a", "ar", "antur")
        + _persons_passive("re", "rer", "rentur")
        + ["ri"]
    )
    conj["i"] = (  # attached to a present stem that ends in -i (audi-)
        _persons("", "o", "unt")
        + _persons("eba", "ebam", "ebant")
        + _persons("e", "am", "ent")
        + _persons("a", "am", "ant")
        + _persons("re", "rem", "rent")
        + ["re", "", "te"]
        + _persons_passive("", "or", "untur")
        + _persons_passive("eba", "ebar", "ebantur")
        + ["ar", "eris", "etur", "emur", "emini", "entur"]
        + _persons_passive("a", "ar", "antur")
        + _persons_passive("re", "rer", "rentur")
        + ["ri"]
    )
    conj["kons"] = (
        _persons("i", "o", "unt")
        + _persons("eba", "ebam", "ebant")
        + _persons("e", "am", "ent")
        + _persons("a", "am", "ant")
        + _persons("ere", "erem", "erent")
        + ["ere", "e", "ite"]
        + _persons_passive("i", "or", "untur")  # note: 2sg is -eris, added below
        + ["eris"]
        + _persons_passive("eba", "ebar", "ebantur")
        + ["ar", "eris", "etur", "emur", "emini", "entur"]
        + _persons_passive("a", "ar", "antur")
        + _persons_passive("ere", "erer", "erentur")
        + ["i"]
    )
    conj["halbkons"] = (  # capio-type
        _persons("i", "io", "iunt")
        + _persons("ieba", "iebam", "iebant")
        + _persons("ie", "iam", "ient")
        + _persons("ia", "iam", "iant")
        + _persons("ere", "erem", "erent")
        + ["ere", "e", "ite"]
        + _persons_passive("i", "ior", "iuntur")
        + ["eris"]
        + _persons_passive("ieba", "iebar", "iebantur")
        + ["iar", "ieris", "ietur", "iemur", "iemini", "ientur"]
        + _persons_passive("ia", "iar", "iantur")
        + _persons_passive("ere", "erer", "erentur")
        + ["i"]
    )
    conj["gem"] = conj["halbkons"]

    return {k: set(v) for k, v in conj.items()}


VERB_SUFFIXES = _conjugation_suffixes()

# (nom. sg. participle, participle stem, gerund stem) suffixes per conjugation
PARTICIPLES = {
    "a": ("ans", "ant", "and"),
    "e": ("ns", "nt", "nd"),  # the present stem already ends in -e
    "i": ("ens", "ent", "end"),
    "kons": ("ens", "ent", "end"),
    "halbkons": ("iens", "ient", "iend"),
    "gem": ("iens", "ient", "iend"),
}

# perfect-system endings (attached to the perfect stem, all conjugations)
PERFECT_SUFFIXES = {
    "i", "isti", "it", "imus", "istis", "erunt", "ere",  # perfect indicative
    "eram", "eras", "erat", "eramus", "eratis", "erant",  # pluperfect
    "ero", "eris", "erit", "erimus", "eritis", "erint",  # fut. perf. / perf. subj.
    "erim",
    "issem", "isses", "isset", "issemus", "issetis", "issent",  # plup. subj.
    "isse",  # perfect infinitive
}


# --------------------------------------------------------------------------
# parsing of the cleaned column format
# --------------------------------------------------------------------------


def _parse_flags(dekl_part: str) -> tuple[str, set[str]]:
    """Split a Deklination part into its base and its (...) flags."""
    part = dekl_part.strip()
    part = re.sub(r"\s*\?$", "", part)  # 'unverified' marker
    flags = set(re.findall(r"\((m\.|f\.|n\.|Adj\.|Pl\.|Dep\.)\)", part))
    base = re.sub(r"\s*\([^)]*\)", "", part).strip()
    return base, flags


def _parse_noun_part(ws_part: str) -> list[str] | None:
    """Stems of a 'stem -ending' part (the ending itself is not needed)."""
    m = re.match(r"^(\S+) -\S+?( \?)?$", ws_part.strip())
    if not m:
        return None
    return m.group(1).split("/")


def _parse_verb_part(ws_part: str) -> list[list[str]] | None:
    """[present stems, perfect stems, supine stems]; [] for a missing stem."""
    stems = [s.strip() for s in ws_part.split(",")]
    if len(stems) != 3:
        return None
    parsed = []
    for stem in stems:
        stem = stem.rstrip("?").strip()
        parsed.append([] if stem == "-" else stem.split("/"))
    return parsed


def _spelling_variants(forms: set[str]) -> set[str]:
    """Add the medieval e-spelling for every ae and vice versa."""
    variants = set(forms)
    for form in forms:
        if "ae" in form:
            variants.add(form.replace("ae", "e"))
    return variants


# --------------------------------------------------------------------------
# form generation
# --------------------------------------------------------------------------


def _noun_or_adj_forms(word: str, stems: list[str], base: str, flags: set[str]) -> set[str] | None:
    endings: set[str] = set()
    for cls in base.split("/"):
        cls = cls.rstrip(".")
        if "Adj." in flags:
            table = ADJ_ENDINGS.get("o/a" if cls in ("o", "a") else cls)
        else:
            key = cls + ("_n" if "n." in flags and f"{cls}_n" in NOUN_ENDINGS else "")
            table = NOUN_ENDINGS.get(key)
        if table is None:
            return None
        singular, plural = table
        if "Pl." in flags:
            endings |= plural
        else:
            endings |= singular | plural
    forms = {word}
    for stem in stems:
        forms |= {stem + e for e in endings}
        # o-declension nominatives in -er/-ir keep the bare stem (presbiter)
        if stem.endswith("r"):
            forms.add(stem)
    return _spelling_variants(forms)


def _verb_forms(word: str, stems: list[list[str]], conj: str, deponent: bool) -> set[str] | None:
    suffixes = VERB_SUFFIXES.get(conj)
    if suffixes is None:
        return None
    present, perfect, supine = stems

    forms = {word}
    for stem in present:
        for suffix in suffixes:
            # deponents have no active finite forms: keep only the passive
            # ones (ending in -r, -ris, -tur, -mur, -mini) and the passive
            # infinitive (-i, -ri, -ari)
            if deponent and not (
                suffix.endswith(("r", "ris", "tur", "mur", "mini"))
                or suffix in ("i", "ri", "ari")
            ):
                continue
            forms.add(stem + suffix)
        # present participle (declines like gem.) and gerund/gerundive
        part_nom, part_stem, gerund_stem = PARTICIPLES[conj]
        forms.add(stem + part_nom)
        forms |= {
            stem + part_stem + e
            for e in NOUN_ENDINGS["gem"][0] | NOUN_ENDINGS["gem"][1] | {"ia"}
        }
        forms |= {
            stem + gerund_stem + e
            for e in ADJ_ENDINGS["o/a"][0] | ADJ_ENDINGS["o/a"][1]
        }
    if not deponent:
        for stem in perfect:
            forms |= {stem + s for s in PERFECT_SUFFIXES}
    for stem in supine:
        # perfect participle and future active participle decline like o/a
        oa = ADJ_ENDINGS["o/a"][0] | ADJ_ENDINGS["o/a"][1]
        forms |= {stem + e for e in oa}
        forms |= {stem + "ur" + e for e in oa}
        forms |= {stem + "um", stem + "u"}
    return _spelling_variants(forms)


def word_forms(word: str, ws_part: str, dekl_part: str) -> set[str] | None:
    """
    All acceptable surface forms for one word of an Auflösung.
    Returns None if the morphology is unknown ('?' or unparseable).
    """
    ws_part = ws_part.strip()
    base, flags = _parse_flags(dekl_part)

    if base == "-" or base == "Adverb":
        return {word} if ws_part == word or ws_part == "?" else None
    if ws_part == "?" or base == "?":
        return None

    if base.endswith("-Konj."):
        stems = _parse_verb_part(ws_part)
        if stems is None:
            return None
        conj = base.removesuffix("-Konj.").rstrip(".")
        return _verb_forms(word, stems, conj, "Dep." in flags)

    if base == "Gerundium":
        stems = _parse_noun_part(ws_part)
        if stems is None:
            return {word}
        return _spelling_variants(
            {word} | {s + e for s in stems for e in ("i", "o", "um")}
        )
    if base == "Gerundivum":
        stems = _parse_noun_part(ws_part)
        if stems is None:
            return {word}
        return _noun_or_adj_forms(word, stems, "o/a", {"Adj."})

    stems = _parse_noun_part(ws_part)
    if stems is None:
        return None
    return _noun_or_adj_forms(word, stems, base, flags)


def entry_forms(
    aufloesung: str | None, wortstamm: str | None, deklination: str | None
) -> list[tuple[str, set[str] | None]] | None:
    """
    Forms for every word of an Auflösung: a list of (word, forms) pairs in
    word order, with forms=None for words whose morphology is unknown.
    Returns None if the entry as a whole cannot be interpreted.
    """
    if not aufloesung or not wortstamm or not deklination:
        return None
    words = aufloesung_words(aufloesung)
    ws_parts = [p.strip() for p in wortstamm.split(";")]
    dekl_parts = [p.strip() for p in deklination.split(";")]
    if not (len(words) == len(ws_parts) == len(dekl_parts)):
        return None
    return [
        (word, word_forms(word, wp, dp))
        for word, wp, dp in zip(words, ws_parts, dekl_parts)
    ]
