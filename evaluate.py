#!/usr/bin/env python3
"""
Step 5: measuring the quality of the expansion against the gold labels.

`data/to_compare_with/fable_expanded.csv` holds a hand-checked expansion for
part of the vitae the workflow has processed. This script compares the output of
every pipeline stage with it, so a change to a prompt, a model or a glossary
entry can be judged by a number instead of by reading the texts.

The unit of measurement is the single abbreviation, not the text: a text-level
diff mixes one expansion error with twenty inflection differences and tells you
nothing actionable. The abbreviated source text is the anchor -- for each vita
the source is aligned with the gold and with the stage output at word level, so
every abbreviation of the source gets a gold expansion and a system expansion
that are compared directly.

The alignment works because the expansion steps only ever replace abbreviations:
every word that was not abbreviated reappears unchanged and in order in both
texts and thus anchors the alignment (the same property `normalize.py` relies
on). Inside a changed block the abbreviations are re-anchored on the expansion
that continues their stem (`eccl.` -> `ecclesiam`), which resolves runs such as
`o. s. Ben. Terdon. dioc.` -> `ordinis sancti Benedicti Terdonensis diocesis`.
Occurrences that cannot be anchored are reported as `unaligned` and left out of
every rate rather than silently scored.

Two rates are reported per stage, because a single exact-match number would
score `thrice_expanded` (deliberately base forms) as broken:

- word accuracy -- was the right word chosen? This is what steps 1-3 do.
- form accuracy -- is the text right as it stands? This is what step 4 moves.

Steps 2 and 3 do not invent an expansion, they choose one from a list, so a
wrong word is only the model's fault if the list held the right one. The
candidate lists the two steps were offered are read back from the dumps the
pipeline wrote and every error is split into a candidate miss (the list could
not have produced the gold word) and a choice error (it could have).

Usage:
    python evaluate.py                  # print the summary
    python evaluate.py --write          # also write data/review/evaluation_*
    python evaluate.py --save-baseline  # store the run as the baseline
    python evaluate.py --baseline       # print the deltas to the baseline
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import polars as pl

import runs
from helper_functions import vita_dfs_to_vita_texts
from normalize import diocese_entries
from paradigm import ADJ_ENDINGS, NOUN_ENDINGS, entry_forms

DATA_DIR = Path("data")
REVIEW_DIR = DATA_DIR / "review"
GOLD_DEFAULT = DATA_DIR / "to_compare_with" / "fable_expanded.csv"
SOURCE = DATA_DIR / "ablaesse_texts.csv"
GLOSSARY = DATA_DIR / "glossary.csv"
COMPARISON = REVIEW_DIR / "runs.md"  # every run against every other


def baseline_path(run: str) -> Path:
    """A baseline belongs to a run: it answers whether *this* chain got better."""
    return runs.run_dir(run) / "evaluation_baseline.json"

# the pipeline stages, in order; the label is what the report calls them. Steps
# 2-4 are run per model and per thinking setting, so which file a stage is comes
# from the run being scored (`runs.py`) -- the source and the rule-based step 1
# are the same for every run.
STAGE_OF_STEP = {1: "once", 2: "twice", 3: "thrice", 4: "normalized"}
LABELS = {
    "source": "abbreviated text",
    "once": "step 1 (rule)",
    "twice": "step 2 (candidates)",
    "thrice": "step 3 (mined)",
    "normalized": "step 4 (normalized)",
}


def stages(run: str) -> list[tuple[str, str, Path]]:
    """
    The stages of one run: the source, and every step its chain has reached.

    A run that has only got as far as step 2 is scored as far as step 2 rather
    than not at all, so a new model can be judged before the rest is re-run.
    """
    found = [("source", LABELS["source"], SOURCE)]
    for number, entry in runs.chain(run):
        name = STAGE_OF_STEP[number]
        found.append((name, LABELS[name], Path(entry["output"])))
    return found


def candidate_dumps(run: str) -> list[tuple[str, Path, str]]:
    """
    The candidate lists the two model steps were offered, as they were dumped.

    The dump belongs to whichever run produced that step, which for an inherited
    step is not the run being scored.
    """
    # the key under which a dump records the text it produced: that text is what
    # ties an entry to a vita (the dumps carry no volume/nr_RG) and at the same
    # time proves that the dump belongs to the output being scored
    keys = {2: "twice_expanded_text", 3: "thrice_expanded_text"}
    found = []
    for number, entry in runs.chain(run):
        if number in keys and entry.get("dump"):
            found.append((STAGE_OF_STEP[number], Path(entry["dump"]), keys[number]))
    return found

# the step each stage attributes an expansion to (the source expands nothing)
STEP_OF_STAGE = {
    "once": "step 1 (rule)",
    "twice": "step 2 (candidates)",
    "thrice": "step 3 (mined)",
    "normalized": "step 4 (normalized)",
}

# same token notion as normalize.py, plus numbers so dates stay anchors
TOKEN = re.compile(r"[A-Za-z]+\.?|\d+")

# shortest glossary expansion that may anchor an abbreviation (build_anchor_index)
MIN_ANCHOR = 4

# shortest stem the `inflectional_variants` fallback accepts
MIN_STEM = 3

# Mismatches that are errors of the gold, not of the pipeline. Following the
# CORRECTIONS convention of extract_glossary.py every entry carries its reason,
# and an entry that no longer matches any occurrence aborts the run, so the
# table cannot go stale. Grows as data/review/evaluation_mismatches.csv is
# reviewed, so the review effort accumulates instead of being repeated.
# (volume, nr_RG, abbreviation, gold_text, reason)
KNOWN_GOLD_ERRORS: list[tuple[int, int, str, str, str]] = []


# --------------------------------------------------------------------------
# orthography and lemmas
# --------------------------------------------------------------------------

def orthographic_key(word: str) -> str:
    """
    The spelling-insensitive key of a word. The RG (and the gold) use the
    medieval spellings interchangeably, so `opidum`/`oppidum`,
    `parochialis`/`parrochialis` and `ecclesiae`/`ecclesie` must not count as
    different expansions.
    """
    key = word.lower().strip(".,;:?!()[]")
    key = key.replace("ae", "e").replace("oe", "e")
    key = key.replace("j", "i").replace("v", "u").replace("y", "i")
    key = re.sub(r"(.)\1+", r"\1", key)  # opidum == oppidum
    return key


def phrase_key(phrase: str) -> str:
    """The orthographic key of a whole expansion (which may be several words)."""
    return " ".join(orthographic_key(word) for word in phrase.split() if word)


# the case endings of paradigm.py, in orthographic-key form; "" lets a bare
# stem count as a form (used by `inflectional_variants`)
CASE_ENDINGS: set[str] = {""} | {
    orthographic_key(ending)
    for table in (NOUN_ENDINGS, ADJ_ENDINGS)
    for singular, plural in table.values()
    for ending in singular | plural
}


def glossary_entries(*paths: Path) -> list[tuple[str, str, str]]:
    """(Auflösung, Wortstamm, Deklination) triples from the glossary CSVs."""
    entries = []
    for path in paths:
        table = pl.read_csv(path).select(["Auflösung", "Wortstamm", "Deklination"])
        entries.extend(table.iter_rows())
    return entries


def build_anchor_index(*paths: Path) -> dict[str, set[str]]:
    """
    abbreviation -> the orthographic keys an expansion of it may start with.

    Most expansions continue the abbreviation (`eccl.` -> `ecclesiam`), which
    the stem rule in `anchor` covers on its own. The glossary supplies the ones
    that do not: `aep.` -> `archiepiscopus`, `d.` -> `quondam`. The inflected
    forms are included, so an anchor is found in the normalized text as well.

    Words shorter than `MIN_ANCHOR` are left out: they are the function words
    (`et` for `etc.`) that occur all over the expansion of the *neighbouring*
    abbreviation and would anchor there instead.
    """
    index: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        table = pl.read_csv(path).select(
            ["Abkürzung", "Auflösung", "Wortstamm", "Deklination"]
        )
        for abbreviation, aufloesung, wortstamm, deklination in table.iter_rows():
            if not abbreviation or not aufloesung:
                continue
            first = aufloesung.split()[0]
            keys = {orthographic_key(first)}
            for word, forms in entry_forms(aufloesung, wortstamm, deklination) or []:
                if word != first:
                    continue  # only the first word can start the expansion
                keys.update(orthographic_key(form) for form in forms or ())
            index[abbreviation].update(key for key in keys if len(key) >= MIN_ANCHOR)
    return dict(index)


def build_lemma_index(entries) -> dict[str, set[str]]:
    """
    orthographic key of a form -> the base forms it can belong to.

    Built from the same paradigms the normalisation step offers the model
    (`paradigm.entry_forms`), so "the right word in the wrong form" is judged by
    exactly the forms step 4 is allowed to choose from.
    """
    index: dict[str, set[str]] = defaultdict(set)
    for aufloesung, wortstamm, deklination in entries:
        for word, forms in entry_forms(aufloesung, wortstamm, deklination) or []:
            index[orthographic_key(word)].add(word)
            for form in forms or ():
                index[orthographic_key(form)].add(word)
    return dict(index)


def shared_prefix(a: str, b: str) -> int:
    common = 0
    for x, y in zip(a, b):
        if x != y:
            break
        common += 1
    return common


def inflectional_variants(a: str, b: str) -> bool:
    """
    Whether two orthographic keys look like two forms of one word: a shared
    stem of at least MIN_STEM letters, and on both sides nothing but a case
    ending (the endings `paradigm.py` attaches to a stem).

    This is the fallback for expansions the glossary knows no morphology for
    (step 3 mines them from the corpus). Requiring real endings is what keeps
    it from accepting a derivation: `nunti|o` / `nunti|us` passes, but
    `assigna|tio` / `assigna|ndi` and `Terdon|is` / `Terdon|ensis` do not.
    """
    for stem in range(shared_prefix(a, b), MIN_STEM - 1, -1):
        if a[stem:] in CASE_ENDINGS and b[stem:] in CASE_ENDINGS:
            return True
    return False


def same_lemma(gold: str, system: str, lemma_index: dict[str, set[str]]) -> str | None:
    """
    "wrong_form" if the two expansions are forms of the same word, "wrong_form?"
    if only the prefix heuristic says so (for expansions outside the glossary:
    step 3's corpus-mined words and the diocese adjectives), None if they are
    different words.

    Multi-word expansions are compared word by word: they are the same lemma
    only if they have the same length and every word matches.
    """
    gold_words, system_words = gold.split(), system.split()
    if not gold_words or len(gold_words) != len(system_words):
        return None

    verdicts = set()
    for gold_word, system_word in zip(gold_words, system_words):
        gold_key, system_key = orthographic_key(gold_word), orthographic_key(system_word)
        if gold_key == system_key:
            continue
        lemmas = lemma_index.get(gold_key, set()) & lemma_index.get(system_key, set())
        if lemmas:
            verdicts.add("wrong_form")
            continue
        if inflectional_variants(gold_key, system_key):
            verdicts.add("wrong_form?")
            continue
        return None
    if not verdicts:
        return None  # every word matched: not a lemma difference at all
    return "wrong_form?" if "wrong_form?" in verdicts else "wrong_form"


# --------------------------------------------------------------------------
# alignment
# --------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text)


def is_abbreviation(token: str) -> bool:
    return token.endswith(".")


def align(
    source: list[str], target: list[str], anchors: dict[str, set[str]] | None = None
) -> list[tuple[int, int] | None]:
    """
    For every source token the span of target tokens it corresponds to, or None
    where no span could be determined.

    Unchanged tokens map one to one; a changed block is sub-aligned with
    `subalign` so that each abbreviation of the block gets its own expansion.
    """
    matcher = SequenceMatcher(a=source, b=target, autojunk=False)
    spans: list[tuple[int, int] | None] = [None] * len(source)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                spans[i1 + k] = (j1 + k, j1 + k + 1)
        elif op == "delete":
            for k in range(i1, i2):
                spans[k] = (j1, j1)  # dropped by the target: empty span
        elif op == "replace":
            for k, span in enumerate(subalign(source[i1:i2], target[j1:j2], anchors)):
                spans[i1 + k] = None if span is None else (j1 + span[0], j1 + span[1])
        # "insert" adds target tokens that belong to no source token
    return spans


def anchor(
    source_token: str,
    target_tokens: list[str],
    start: int,
    anchors: dict[str, set[str]] | None = None,
) -> int | None:
    """
    Index of the first target token at or after `start` that can be the
    beginning of the source token's expansion: normally one whose orthographic
    key continues the abbreviation's stem (`eccl.` anchors on `ecclesiam`,
    `s.` on `sancti`), otherwise one the glossary lists as an expansion of it
    (`aep.` -> `archiepiscopus`, see `build_anchor_index`).
    """
    stem = orthographic_key(source_token)
    if not stem:
        return None
    known = (anchors or {}).get(source_token, set())
    for index in range(start, len(target_tokens)):
        key = orthographic_key(target_tokens[index])
        if key.startswith(stem) or key in known:
            return index
    return None


def subalign(
    source: list[str], target: list[str], anchors: dict[str, set[str]] | None = None
) -> list[tuple[int, int] | None]:
    """
    Distribute a changed block's target tokens over its source tokens.

    Each source token is anchored on the target token that begins its
    expansion; its span then reaches to the start of the next source token's
    span, so both a one-to-many expansion (`m. evoc.` -> `mandatum evocandi`)
    and a many-to-one one are covered without two source tokens ever claiming
    the same target token.

    A single source token between two anchored ones gets exactly what lies
    between them -- that is how `aep. etc.` -> `archiepiscopus, prepositus,
    decanus et canonici` is split, where `etc.` cannot be anchored. A run of
    several unanchored tokens is genuinely ambiguous: its tokens are given a
    proportional share so the block's boundaries stay consistent, but they are
    reported as `unaligned` instead of being scored.
    """
    if len(source) == len(target) == 1:
        return [(0, 1)]

    found: dict[int, int] = {}
    position = 0
    for index, token in enumerate(source):
        at = anchor(token, target, position, anchors)
        if at is not None:
            found[index] = at
            position = at + 1

    starts: list[int] = [0] * len(source)
    aligned: list[bool] = [False] * len(source)
    index = 0
    while index < len(source):
        if index in found:
            starts[index], aligned[index] = found[index], True
            index += 1
            continue
        end = index
        while end < len(source) and end not in found:
            end += 1
        low = 0 if index == 0 else starts[index - 1] + (1 if index - 1 in found else 0)
        high = found[end] if end < len(source) else len(target)
        high = max(high, low)
        if end - index == 1:
            starts[index], aligned[index] = low, True
        else:
            width = (high - low) / (end - index)
            for k in range(index, end):
                starts[k] = low + round(width * (k - index))
        index = end

    spans: list[tuple[int, int] | None] = []
    for index in range(len(source)):
        stop = starts[index + 1] if index + 1 < len(source) else len(target)
        spans.append((starts[index], max(stop, starts[index])) if aligned[index] else None)
    return spans


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

@dataclass
class Occurrence:
    """One abbreviation of one vita, with what the gold and a stage made of it."""

    volume: int
    nr_RG: int
    abbreviation: str
    gold: str
    context: str
    stage_expansions: dict[str, str | None] = field(default_factory=dict)
    verdicts: dict[str, str] = field(default_factory=dict)
    step: str | None = None  # the stage that expanded it (in the last stage)
    candidates: dict[str, list[str]] = field(default_factory=dict)  # per stage
    covered: dict[str, bool] = field(default_factory=dict)  # gold among them?


def verdict(gold: str, system: str | None, lemma_index) -> str:
    """The verdict for one abbreviation in one stage (see the module docstring)."""
    if system is None:
        return "unaligned"
    if not system.strip():
        return "not_expanded"
    if any(is_abbreviation(token) for token in system.split()):
        return "not_expanded"
    if gold == system:
        return "exact"
    if phrase_key(gold) == phrase_key(system):
        return "orthographic"
    return same_lemma(gold, system, lemma_index) or "wrong_word"


def candidate_covers(gold: str, offered: list[str], lemma_index) -> bool:
    """
    Would any of the offered candidates have counted as the right word?

    The same yardstick as everywhere else in the report: a candidate covers the
    gold if choosing it would have scored `exact`, `orthographic` or one of the
    two `wrong_form` verdicts, i.e. if only the inflection would have been left
    to fix. The candidates of step 2 are base forms and those of step 3 surface
    forms, so the comparison has to run through the lemma check either way.
    """
    return any(verdict(gold, candidate, lemma_index) in CORRECT_WORD
               for candidate in offered)


def span_text(tokens: list[str], span: tuple[int, int] | None) -> str | None:
    if span is None:
        return None
    return " ".join(tokens[span[0]:span[1]])


def evaluate_vita(
    volume: int,
    nr_RG: int,
    source_text: str,
    gold_text: str,
    stage_texts: dict[str, str],
    lemma_index: dict[str, set[str]],
    anchors: dict[str, set[str]] | None = None,
) -> list[Occurrence]:
    """Every abbreviation of one vita, scored in every stage."""
    source = tokenize(source_text)
    gold_tokens = tokenize(gold_text)
    gold_spans = align(source, gold_tokens, anchors)

    stage_tokens = {name: tokenize(text) for name, text in stage_texts.items()}
    stage_spans = {
        name: align(source, tokens, anchors) for name, tokens in stage_tokens.items()
    }

    occurrences = []
    for index, token in enumerate(source):
        if not is_abbreviation(token):
            continue
        gold = span_text(gold_tokens, gold_spans[index])
        occurrence = Occurrence(
            volume=volume,
            nr_RG=nr_RG,
            abbreviation=token,
            gold=gold if gold is not None else "",
            context=" ".join(source[max(0, index - 4):index + 5]),
        )
        for name in stage_texts:
            occurrence.stage_expansions[name] = span_text(
                stage_tokens[name], stage_spans[name][index]
            )

        if gold is None:
            occurrence.verdicts = {name: "unaligned" for name in stage_texts}
        elif not gold.strip() or any(is_abbreviation(w) for w in gold.split()):
            # the gold left the abbreviation standing (etc., apr., initials) or
            # dropped the passage: there is nothing to compare against
            occurrence.verdicts = {name: "no_gold_label" for name in stage_texts}
        else:
            occurrence.verdicts = {
                name: verdict(gold, occurrence.stage_expansions[name], lemma_index)
                for name in stage_texts
            }
        occurrence.step = attribute(occurrence, source[index])
        occurrences.append(occurrence)
    return occurrences


def attribute(occurrence: Occurrence, abbreviation: str) -> str | None:
    """
    The step that produced the final expansion: the first stage whose expansion
    differs from the abbreviation, refined to step 4 if the normalisation
    changed the form again.
    """
    step = None
    previous = abbreviation
    for name in STEP_OF_STAGE:
        current = occurrence.stage_expansions.get(name)
        if current is None:
            continue
        if step is None and not any(is_abbreviation(w) for w in current.split()):
            step = STEP_OF_STAGE[name]
        elif step is not None and current != previous:
            step = STEP_OF_STAGE[name]  # a later step changed it again
        previous = current
    return step


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def load_texts(path: Path, keys: pl.DataFrame) -> dict[tuple[int, int], str]:
    """
    One text per vita, restricted to `keys`. Files that are already one row per
    vita (a `text` column) are used as they are; the per-regest stage outputs
    are collapsed with the same helper the pipeline itself uses.
    """
    table = pl.read_csv(path)
    table = table.join(keys, on=["volume", "nr_RG"], how="inner")
    if "text" not in table.columns:
        table = vita_dfs_to_vita_texts(table)
    return {(row["volume"], row["nr_RG"]): row["text"] for row in table.iter_rows(named=True)}


def load_candidates(
    path: Path, text_key: str, stage_texts: dict[tuple[int, int], str]
) -> dict[tuple[int, int], dict[str, list[str]]]:
    """
    The candidate list every abbreviation was offered, per vita.

    An entry counts only if the text it records is exactly the stage text being
    scored -- a dump left over from an earlier run must not be counted against
    this one. Entries that do not match, and a missing dump, are silently
    dropped; the report states how many occurrences ended up without a list.
    """
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as file:
        dump = json.load(file)
    # run_step.py wraps the per-vita records in the run's provenance; the dumps
    # the notebooks wrote are the bare list
    entries = dump["results"] if isinstance(dump, dict) else dump
    key_of_text = {text: key for key, text in stage_texts.items()}
    candidates = {}
    for entry in entries:
        key = key_of_text.get(entry.get(text_key))
        if key is not None:
            candidates[key] = {
                abbreviation: list(offered)
                for abbreviation, offered in entry.get("candidates", {}).items()
            }
    return candidates


def collect(gold_path: Path, run: str) -> tuple[list[Occurrence], list[str], dict]:
    """Score every vita that has a gold label. Returns (occurrences, stages, info)."""
    gold_table = pl.read_csv(gold_path)
    keys = gold_table.select(["volume", "nr_RG"]).unique()
    gold = {(row["volume"], row["nr_RG"]): row["text"] for row in gold_table.iter_rows(named=True)}

    of_the_run = stages(run)
    texts = {name: load_texts(path, keys) for name, _, path in of_the_run}
    source = texts.pop("source")
    stage_names = [name for name, _, _ in of_the_run if name != "source"]

    scored = sorted(set(gold) & set(source) & set.intersection(*(set(texts[n]) for n in stage_names)))
    occurrences = []
    lemma_index = build_lemma_index(
        glossary_entries(GLOSSARY)
        + diocese_entries(pl.read_csv(DATA_DIR / "dioceses.csv")["expansion"].to_list())
    )
    anchors = build_anchor_index(GLOSSARY)
    offered = {
        stage: load_candidates(path, text_key, texts[stage])
        for stage, path, text_key in candidate_dumps(run)
    }
    for key in scored:
        scored_vita = evaluate_vita(
            key[0], key[1], source[key], gold[key],
            {name: texts[name][key] for name in stage_names}, lemma_index, anchors,
        )
        for occurrence in scored_vita:
            for stage, table in offered.items():
                candidates = table.get(key, {}).get(occurrence.abbreviation)
                if candidates is None:
                    continue
                occurrence.candidates[stage] = candidates
                occurrence.covered[stage] = candidate_covers(
                    occurrence.gold, candidates, lemma_index
                )
        occurrences.extend(scored_vita)

    info = {
        "gold": str(gold_path),
        "run": run,
        "produced_by": {str(number): entry for number, entry in runs.chain(run)},
        "vitae_with_gold": len(gold),
        "vitae_scored": len(scored),
        "vitae_missing": sorted(set(gold) - set(scored)),
    }
    return occurrences, stage_names, info


def drop_known_gold_errors(occurrences: list[Occurrence]) -> list[Occurrence]:
    """
    Remove the documented gold errors and abort on entries that no longer match
    (the table must not go stale, cf. extract_glossary.CORRECTIONS).
    """
    if not KNOWN_GOLD_ERRORS:
        return occurrences
    wanted = {(v, n, a, g) for v, n, a, g, _ in KNOWN_GOLD_ERRORS}
    kept, matched = [], set()
    for occurrence in occurrences:
        key = (occurrence.volume, occurrence.nr_RG, occurrence.abbreviation, occurrence.gold)
        if key in wanted:
            matched.add(key)
            continue
        kept.append(occurrence)
    stale = wanted - matched
    if stale:
        raise SystemExit(
            "KNOWN_GOLD_ERRORS entries match nothing any more:\n"
            + "\n".join(f"  {entry}" for entry in sorted(stale))
        )
    return kept


# --------------------------------------------------------------------------
# summary and report
# --------------------------------------------------------------------------

CORRECT_WORD = {"exact", "orthographic", "wrong_form", "wrong_form?"}
CORRECT_FORM = {"exact", "orthographic"}
SCOREABLE = CORRECT_WORD | {"wrong_word", "not_expanded"}


def rates(counts: Counter) -> dict:
    scoreable = sum(counts[v] for v in SCOREABLE)
    return {
        "occurrences": sum(counts.values()),
        "scoreable": scoreable,
        "word_accuracy": sum(counts[v] for v in CORRECT_WORD) / scoreable if scoreable else 0.0,
        "form_accuracy": sum(counts[v] for v in CORRECT_FORM) / scoreable if scoreable else 0.0,
        "expanded": (scoreable - counts["not_expanded"]) / scoreable if scoreable else 0.0,
        "counts": dict(counts),
    }


def summarize(occurrences: list[Occurrence], stages: list[str], info: dict) -> dict:
    per_stage = {}
    for name in stages:
        per_stage[name] = rates(Counter(o.verdicts[name] for o in occurrences))

    final = stages[-1]
    by_abbreviation = {}
    for abbreviation in {o.abbreviation for o in occurrences}:
        subset = [o for o in occurrences if o.abbreviation == abbreviation]
        counts = Counter(o.verdicts[final] for o in subset)
        wrong = Counter(
            o.stage_expansions[final]
            for o in subset
            if o.verdicts[final] in {"wrong_word", "wrong_form", "wrong_form?"}
        )
        entry = rates(counts)
        entry["most_frequent_error"] = wrong.most_common(1)[0][0] if wrong else ""
        entry["gold_variants"] = ", ".join(sorted({o.gold for o in subset})[:5])
        by_abbreviation[abbreviation] = entry

    by_step = {}
    for step in sorted({o.step for o in occurrences if o.step}):
        subset = [o for o in occurrences if o.step == step]
        by_step[step] = rates(Counter(o.verdicts[final] for o in subset))

    return {"info": info, "stages": per_stage, "by_abbreviation": by_abbreviation,
            "by_step": by_step, "candidates": candidate_summary(occurrences, final),
            "final_stage": final}


def candidate_summary(occurrences: list[Occurrence], final: str) -> dict:
    """
    How much of each choosing step's error the candidate list is to blame for.

    Only the steps whose candidates were dumped appear. `ceiling` is the share
    of the occurrences whose list held a word that would have scored as right;
    `choice_accuracy` is the word accuracy over exactly those, i.e. the score
    the step gets for the choices it could actually have made. Step 3 may also
    expand freely, so for it the ceiling is not a limit but a measure of how
    often the mined suggestions were enough -- `beyond` counts the right
    answers it found outside them.
    """
    summary = {}
    for stage, step in STEP_OF_STAGE.items():
        subset = [o for o in occurrences
                  if o.step == step and o.verdicts[final] in SCOREABLE]
        offered = [o for o in subset if stage in o.candidates]
        if not offered:
            continue
        right = [o for o in offered if o.verdicts[final] in CORRECT_WORD]
        covered = [o for o in offered if o.covered[stage]]
        chosen_well = [o for o in covered if o.verdicts[final] in CORRECT_WORD]
        misses = [o for o in offered
                  if not o.covered[stage] and o.verdicts[final] not in CORRECT_WORD]
        summary[step] = {
            "expansions": len(offered),
            "without_candidates": len(subset) - len(offered),
            "word_accuracy": len(right) / len(offered),
            "ceiling": len(covered) / len(offered),
            "choice_accuracy": len(chosen_well) / len(covered) if covered else 0.0,
            "errors": len(offered) - len(right),
            "candidate_misses": len(misses),
            "beyond": len(right) - len(chosen_well),
            "worst": Counter(o.abbreviation for o in misses).most_common(5),
        }
    return summary


def headline(summary: dict) -> dict:
    """The numbers that --baseline compares (everything else is detail)."""
    return {
        name: {key: round(stage[key], 6) for key in
               ("word_accuracy", "form_accuracy", "expanded")}
        | {"scoreable": stage["scoreable"]}
        for name, stage in summary["stages"].items()
    }


def percent(value: float) -> str:
    return f"{value * 100:5.1f}%"


def describe_settings(entry: dict) -> str:
    """What was asked of the model's thinking, as the manifest recorded it."""
    if entry.get("reasoning_effort"):
        return f"effort {entry['reasoning_effort']}"
    if entry.get("thinking") is None:
        return "default"
    return "on" if entry["thinking"] else "off"


def produced_by(info: dict) -> list[str]:
    """
    What produced every step of the chain being scored.

    A step can come from another run (`run_step.py --from`), so the run a number
    belongs to is worth stating next to it rather than assumed from the heading.
    """
    lines = ["## What produced this", "",
             "| step | model | thinking | run | written |",
             "| --- | --- | --- | --- | --- |"]
    for number, entry in sorted(info["produced_by"].items(), key=lambda item: int(item[0])):
        if entry.get("model") is None:  # step 1 applies rules, no model involved
            lines.append(f"| step {number} | rule (`expand_simple.py`) | | | |")
            continue
        lines.append(
            f"| step {number} | `{entry['model']}` | {describe_settings(entry)} "
            f"| `{entry.get('run') or ''}` | {entry.get('written') or 'unrecorded'} |"
        )
    return lines + [""]


def render_report(summary: dict, occurrences: list[Occurrence]) -> str:
    info, stages = summary["info"], summary["stages"]
    final = summary["final_stage"]
    labels = LABELS

    lines = [
        f"# Evaluation of `{info['run']}` against the gold labels",
        "",
        f"Gold: `{info['gold']}` -- {info['vitae_scored']} of {info['vitae_with_gold']} "
        "vitae scored (the rest are missing from a pipeline stage).",
        "",
        *produced_by(info),
        "## Accuracy per stage",
        "",
        "Word accuracy asks whether the right word was chosen (steps 1-3), form "
        "accuracy whether the text is right as it stands (step 4).",
        "",
        "| stage | scoreable | expanded | word accuracy | form accuracy | exact | "
        "orthographic | wrong form | wrong form? | wrong word | not expanded |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, stage in stages.items():
        counts = stage["counts"]
        lines.append(
            f"| {labels[name]} | {stage['scoreable']} | {percent(stage['expanded'])} | "
            f"{percent(stage['word_accuracy'])} | {percent(stage['form_accuracy'])} | "
            f"{counts.get('exact', 0)} | {counts.get('orthographic', 0)} | "
            f"{counts.get('wrong_form', 0)} | {counts.get('wrong_form?', 0)} | "
            f"{counts.get('wrong_word', 0)} | {counts.get('not_expanded', 0)} |"
        )

    total = stages[final]["occurrences"]
    no_label = stages[final]["counts"].get("no_gold_label", 0)
    unaligned = stages[final]["counts"].get("unaligned", 0)
    lines += [
        "",
        "## Reliability",
        "",
        f"- {total} abbreviation occurrences in the source of the scored vitae.",
        f"- {no_label} ({no_label / total:.1%}) have no gold label: the gold left the "
        "abbreviation standing (`etc.`, month names, place initials) or dropped the "
        "passage. They are excluded from every rate -- the pipeline may well have "
        "expanded them correctly.",
        f"- {unaligned} ({unaligned / total:.1%}) could not be aligned and are excluded "
        "as well. A rising number here means the metric, not the pipeline, is degrading.",
        f"- {stages[final]['counts'].get('wrong_form?', 0)} `wrong form?` verdicts rest on "
        "the stem-and-ending check that stands in for the paradigm where the glossary "
        "knows no morphology (step 3 mines those words from the corpus). They count as "
        "the right word, so word accuracy carries that much uncertainty. Step 4 cannot "
        "change a word, only its form -- a small dip in word accuracy there is this "
        "check reacting to the new ending, not the pipeline losing a word.",
    ]
    if KNOWN_GOLD_ERRORS:
        lines += ["", f"- {len(KNOWN_GOLD_ERRORS)} documented gold errors were excluded "
                  "(see `KNOWN_GOLD_ERRORS` in evaluate.py)."]

    lines += ["", "## Errors by step", "",
              "Which step produced the expansion that is finally in the text.", "",
              "| step | expansions | word accuracy | form accuracy |",
              "| --- | ---: | ---: | ---: |"]
    for step, stage in summary["by_step"].items():
        lines.append(f"| {step} | {stage['scoreable']} | "
                     f"{percent(stage['word_accuracy'])} | {percent(stage['form_accuracy'])} |")

    lines += render_candidates(summary["candidates"])

    lines += ["", "## Worst abbreviations", "",
              "Sorted by how many occurrences fixing them would gain.", "",
              "| abbreviation | occurrences | word accuracy | form accuracy | "
              "most frequent wrong expansion | gold |",
              "| --- | ---: | ---: | ---: | --- | --- |"]
    ranked = sorted(
        summary["by_abbreviation"].items(),
        key=lambda item: -item[1]["scoreable"] * (1 - item[1]["form_accuracy"]),
    )
    for abbreviation, stage in ranked[:25]:
        if stage["scoreable"] == 0 or stage["form_accuracy"] == 1.0:
            continue
        lines.append(
            f"| `{abbreviation}` | {stage['scoreable']} | {percent(stage['word_accuracy'])} | "
            f"{percent(stage['form_accuracy'])} | {stage['most_frequent_error']} | "
            f"{stage['gold_variants']} |"
        )

    lines += ["", "## Sample mismatches", "",
              "The full list is in `evaluation_mismatches.csv`.", ""]
    for occurrence in occurrences:
        if occurrence.verdicts[final] not in {"wrong_word", "not_expanded"}:
            continue
        lines.append(
            f"- {occurrence.volume}/{occurrence.nr_RG} `{occurrence.abbreviation}`: "
            f"gold **{occurrence.gold}**, system **{occurrence.stage_expansions[final]}** "
            f"({occurrence.step}) -- _{occurrence.context}_"
        )
        if len(lines) > 120 + len(stages):
            lines.append("- ...")
            break
    return "\n".join(lines) + "\n"


def render_candidates(candidates: dict) -> list[str]:
    """The candidate-coverage section: how much of the error is the list's."""
    if not candidates:
        return []
    lines = [
        "", "## Candidate coverage", "",
        "Steps 2 and 3 do not invent an expansion, they choose one from a list, so "
        "an error is only the model's if the list held the right word. `ceiling` is "
        "the share of the expansions whose list did; `choice accuracy` scores the "
        "step over exactly those, i.e. over the choices it could have made.",
        "",
        "| step | expansions | word accuracy | ceiling | choice accuracy | errors | "
        "candidate misses |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for step, entry in candidates.items():
        misses = entry["candidate_misses"]
        share = f" ({misses / entry['errors']:.0%})" if entry["errors"] else ""
        lines.append(
            f"| {step} | {entry['expansions']} | {percent(entry['word_accuracy'])} | "
            f"{percent(entry['ceiling'])} | {percent(entry['choice_accuracy'])} | "
            f"{entry['errors']} | {misses}{share} |"
        )
    lines.append("")
    for step, entry in candidates.items():
        if entry["worst"]:
            worst = ", ".join(f"`{a}` ({n})" for a, n in entry["worst"])
            lines.append(f"- {step}: the candidate misses are mostly {worst}.")
        if entry["beyond"]:
            lines.append(
                f"- {step}: {entry['beyond']} of its right answers were not in its "
                "list at all -- the step may expand freely as long as the expansion "
                "extends the abbreviation, so for it the list is a hint, not a limit."
            )
        if entry["without_candidates"]:
            lines.append(
                f"- {step}: {entry['without_candidates']} expansions have no recorded "
                "list (a multi-word abbreviation is offered under its whole key, not "
                "under its parts) and are left out of this table."
            )
    lines.append(
        "- A candidate counts as covering the gold under the same yardstick as the "
        "rest of the report, so a candidate the lemma check cannot connect to the "
        "gold form -- verbs above all, which the glossary gives no paradigm -- is "
        "counted as a miss although it is in truth the right word. The candidate "
        "miss column is therefore an upper bound."
    )
    return lines


def mismatch_table(occurrences: list[Occurrence], stages: list[str]) -> pl.DataFrame:
    final = stages[-1]
    rows = [
        {
            "volume": o.volume,
            "nr_RG": o.nr_RG,
            "abbreviation": o.abbreviation,
            "gold": o.gold,
            "system": o.stage_expansions[final] or "",
            "verdict": o.verdicts[final],
            "step": o.step or "",
            "candidate_miss": candidate_miss(o),
            "candidates": "; ".join(step_candidates(o)),
            **{f"verdict_{name}": o.verdicts[name] for name in stages[:-1]},
            **{f"expansion_{name}": o.stage_expansions[name] or "" for name in stages[:-1]},
            "context": o.context,
        }
        for o in occurrences
        if o.verdicts[final] != "exact"
    ]
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort(["verdict", "abbreviation", "volume", "nr_RG"])


def step_candidates(occurrence: Occurrence) -> list[str]:
    """The list the step that produced the final expansion had to choose from."""
    for stage, step in STEP_OF_STAGE.items():
        if occurrence.step == step:
            return occurrence.candidates.get(stage, [])
    return []


def candidate_miss(occurrence: Occurrence) -> str:
    """Whether that list could have produced the gold word at all."""
    for stage, step in STEP_OF_STAGE.items():
        if occurrence.step == step and stage in occurrence.covered:
            return "no" if occurrence.covered[stage] else "yes"
    return ""


def abbreviation_table(summary: dict) -> pl.DataFrame:
    rows = [
        {
            "abbreviation": abbreviation,
            "occurrences": stage["scoreable"],
            "word_accuracy": round(stage["word_accuracy"], 4),
            "form_accuracy": round(stage["form_accuracy"], 4),
            "no_gold_label": stage["counts"].get("no_gold_label", 0),
            "most_frequent_error": stage["most_frequent_error"],
            "gold_variants": stage["gold_variants"],
        }
        for abbreviation, stage in summary["by_abbreviation"].items()
    ]
    return pl.DataFrame(rows).with_columns(
        (pl.col("occurrences") * (1 - pl.col("form_accuracy"))).alias("potential_gain")
    ).sort("potential_gain", descending=True)


def render_baseline_diff(current: dict, previous: dict) -> str:
    labels = LABELS
    lines = ["", "Change against the baseline:", ""]
    for name, stage in current.items():
        old = previous.get(name)
        if old is None:
            lines.append(f"  {labels.get(name, name):24} (new stage)")
            continue
        parts = []
        for key in ("word_accuracy", "form_accuracy", "expanded"):
            delta = (stage[key] - old[key]) * 100
            parts.append(f"{key.replace('_', ' ')} {delta:+.2f}pp")
        if stage["scoreable"] != old["scoreable"]:
            parts.append(f"scoreable {stage['scoreable'] - old['scoreable']:+d}")
        lines.append(f"  {labels.get(name, name):24} " + ", ".join(parts))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def score(gold_path: Path, run: str) -> tuple[dict, list[Occurrence], list[str]]:
    """One run scored: its summary, its occurrences and the stages it reached."""
    occurrences, stage_names, info = collect(gold_path, run)
    occurrences = drop_known_gold_errors(occurrences)
    return summarize(occurrences, stage_names, info), occurrences, stage_names


def evaluate(gold_path: Path, run: str, write: bool, baseline: bool,
             save_baseline: bool) -> dict:
    summary, occurrences, stages = score(gold_path, run)
    report = render_report(summary, occurrences)
    baseline_file = baseline_path(run)

    print(report)

    if baseline:
        if baseline_file.exists():
            with open(baseline_file, encoding="utf-8") as file:
                print(render_baseline_diff(headline(summary), json.load(file)["stages"]))
        else:
            print(f"\nno baseline for {run} yet -- run with --save-baseline "
                  f"to create {baseline_file}")

    if write:
        directory = runs.run_dir(run)
        directory.mkdir(parents=True, exist_ok=True)
        with open(directory / "evaluation_report.md", "w", encoding="utf-8") as file:
            file.write(report)
        mismatches = mismatch_table(occurrences, stages)
        if not mismatches.is_empty():
            mismatches.write_csv(directory / "evaluation_mismatches.csv")
        abbreviation_table(summary).write_csv(directory / "evaluation_by_abbreviation.csv")
        print(f"Wrote {directory}/evaluation_*.")
    else:
        print(f"\ndry run -- pass --write to update {runs.run_dir(run)}/evaluation_*")

    if save_baseline:
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        with open(baseline_file, "w", encoding="utf-8") as file:
            json.dump({"gold": str(gold_path), "run": run, "stages": headline(summary)},
                      file, indent=2)
        print(f"Saved the current numbers as the baseline in {baseline_file}.")

    return summary


def model_cell(entry: dict) -> str:
    """The model of one step of a chain, as a table cell."""
    return f"`{entry['model']} ({describe_settings(entry)})`"


def step_section(step: int, scored: list[tuple[str, dict, dict]]) -> list[str]:
    """
    One step of every chain that has it, scored on the text that step produced.

    The table at the top of the file scores each run where it has got to, which
    answers "which chain is best so far" but not "which model should do step 2":
    a run that has been taken through step 4 is scored on a normalised text, one
    that stopped at step 2 on an uninflected one, and the two numbers are not
    the same question. Here every row is the same stage.

    Steps 2 and 3 are read by word accuracy -- whether the right word was
    chosen; the inflection is step 4's business, and form accuracy at these
    stages mostly measures how much of it is still to do. Step 4 is read by form
    accuracy, which is the only thing it can move.

    `gained` is the rise over the stage before it in that same chain. For step 2
    every chain starts from the same rule-based text, so the column adds little;
    for steps 3 and 4, which build on whatever their own step 2 produced, it is
    the part of the number the step is actually responsible for.

    A step that several runs share -- one run took it from another with `--from`
    -- is one row, under the run that produced it: the file, and so the score,
    is the same one.
    """
    stage, before = STAGE_OF_STEP[step], STAGE_OF_STEP[step - 1]
    measure = "form" if step == 4 else "word"
    rows, seen = [], set()
    for name, summary, chain in scored:
        if stage not in summary["stages"] or step not in chain:
            continue
        produced = chain[step].get("output")
        if produced in seen:
            continue
        seen.add(produced)
        reached, previously = summary["stages"][stage], summary["stages"][before]
        rows.append({
            "run": chain[step].get("run") or name,
            "models": [model_cell(chain[number]) for number in range(2, step + 1)],
            "word": reached["word_accuracy"],
            "form": reached["form_accuracy"],
            "gained": reached[f"{measure}_accuracy"] - previously[f"{measure}_accuracy"],
            "scoreable": reached["scoreable"],
        })
    if not rows:
        return []
    rows.sort(key=lambda row: -row[measure])

    said = ("whether the right word was chosen" if measure == "word"
            else "whether the text is right as it stands")
    columns = " | ".join(f"step {number}" for number in range(2, step + 1))
    lines = [
        f"## Step {step} on its own",
        "",
        f"Every chain that has a step {step}, scored on the text it produced -- so the "
        f"rows are comparable whatever the runs did afterwards. Sorted by "
        f"{measure} accuracy, which asks {said}; `gained` is the rise over "
        f"{LABELS[before]} in the same chain.",
        "",
        f"| produced by | {columns} | word accuracy | form accuracy | gained | scoreable |",
        "| --- | " + "--- | " * (step - 1) + "---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(f"| `{row['run']}` | {' | '.join(row['models'])} | "
                     f"{percent(row['word'])} | {percent(row['form'])} | "
                     f"{row['gained'] * 100:+5.1f}pp | {row['scoreable']} |")
    return lines + [""]


def compare(gold_path: Path, names: list[str]) -> str:
    """
    Every run in one table: which model did which step, and what came of it.

    The rates are those of the last stage a run has reached, so a chain that
    stops at step 2 is listed with what it did reach rather than left out --
    the stage is named in its own column so the rows stay comparable. What that
    table cannot answer is which model to give a single step to, since it scores
    the runs at different stages; the sections after it do, one per step.
    """
    scored = [(name, score(gold_path, name)[0], dict(runs.chain(name)))
              for name in names]
    rows = []
    for name, summary, steps in scored:
        final = summary["stages"][summary["final_stage"]]
        rows.append({
            "run": name,
            "models": [f"{steps[number]['model']} ({describe_settings(steps[number])})"
                       if number in steps else "" for number in (2, 3, 4)],
            "final": LABELS[summary["final_stage"]],
            "word": final["word_accuracy"],
            "form": final["form_accuracy"],
            "scoreable": final["scoreable"],
        })
    rows.sort(key=lambda row: (-row["form"], -row["word"]))

    lines = [
        "# The runs against each other",
        "",
        f"Gold: `{gold_path}`. Word accuracy asks whether the right word was chosen, "
        "form accuracy whether the text is right as it stands; both are those of the "
        "last stage the run reached.",
        "",
        "| run | step 2 | step 3 | step 4 | scored at | word accuracy | form accuracy |",
        "| --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    for row in rows:
        models = " | ".join(f"`{model}`" if model else "—" for model in row["models"])
        lines.append(f"| `{row['run']}` | {models} | {row['final']} | "
                     f"{percent(row['word'])} | {percent(row['form'])} |")
    lines.append("")
    for step in (2, 3, 4):
        lines += step_section(step, scored)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score the expansion pipeline against the gold labels."
    )
    parser.add_argument("--gold", type=Path, default=GOLD_DEFAULT,
                        help=f"the gold CSV (default: {GOLD_DEFAULT})")
    parser.add_argument("--run", help="which run to score (default: the only one there is)")
    parser.add_argument("--runs", action="store_true",
                        help=f"score every run and write {COMPARISON}")
    parser.add_argument("--write", action="store_true",
                        help="write data/runs/<run>/evaluation_* (default: dry run)")
    parser.add_argument("--baseline", action="store_true",
                        help="print the change against this run's saved baseline")
    parser.add_argument("--save-baseline", action="store_true",
                        help="store the current numbers as this run's baseline")
    arguments = parser.parse_args()

    if arguments.runs:
        names = runs.existing_runs()
        if not names:
            raise SystemExit(f"no run in {runs.RUNS_DIR} yet")
        table = compare(arguments.gold, names)
        print(table)
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        COMPARISON.write_text(table, encoding="utf-8")
        print(f"Wrote {COMPARISON}.")
        return

    try:
        run = runs.the_run(arguments.run)
    except LookupError as error:
        raise SystemExit(str(error))
    evaluate(arguments.gold, run, arguments.write, arguments.baseline,
             arguments.save_baseline)


if __name__ == "__main__":
    main()
