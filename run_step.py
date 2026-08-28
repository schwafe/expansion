#!/usr/bin/env python3
"""
Steps 2-4: the three model-driven passes over the vitae.

The three steps differ only in what they ask the model and what they let it
answer -- step 2 chooses among the glossary candidates, step 3 expands what has
no glossary entry, step 4 inflects what the earlier steps inserted. The loop
around them is the same: read the output of the previous step, take one vita at
a time, mark the occurrences, ask the model, substitute its answer
programmatically, record what happened. That loop lives here, once; the
per-step work is in `multiple_choice.py`, `expand_rest.py` and `normalize.py`.

Everything the model may change is decided before the call and checked after
it, so a bad answer can only leave the text as it was:

- step 2 accepts only a candidate from the list it offered,
- step 3 accepts only an expansion that continues the letters of the
  abbreviation (or `SKIP`),
- step 4 accepts only a form from the word's own paradigm.

**Checkpoints.** A run is 150+ model calls at 15 calls a minute, so it has to
survive being interrupted. Every vita is appended to
`data/checkpoints/step<n>.jsonl` as it is finished (flushed every ten by
default); `--resume` reads that file and processes only what is missing. The
CSV and the JSON dump are written only once every vita is done -- an
interrupted run never overwrites a complete output with a partial one.

Usage:
    python run_step.py 2                       # the whole subset
    python run_step.py 3 --limit 5             # a trial run, writes no output
    python run_step.py 4 --resume              # continue an interrupted run
    python run_step.py 2 --model qwen3.6-35b-a3b
    python run_step.py 2 --model gemma-4-31b-it --no-thinking
    python run_step.py 2 --model qwen3.8-27b --reasoning-effort low

**Thinking.** The reasoning models think by default, which on a whole vita can
take minutes per call and rarely changes the answer, since every step is a
choice from a list. `--no-thinking` turns it off, `--reasoning-effort` sets how
much of it there is; passing neither leaves the model at its default. Every
family takes these differently and ignores what it does not know without a
word, so the request is built from the table in `helper_functions.STYLES` and
anything the model cannot do is refused before the run starts. What a run used
is recorded in the dump next to the model name.
"""

import argparse
import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import polars as pl
from dotenv import load_dotenv
from openai import OpenAI

import expand_rest
import multiple_choice
import normalize
from helper_functions import (
    call_chat_ai,
    determine_candidates,
    known_efforts,
    text_to_vita_df,
    thinking_kwargs,
    vita_df_to_text,
)

DATA_DIR = Path("data")
REVIEW_DIR = DATA_DIR / "review"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"

RG = DATA_DIR / "RG_header_sublemma_all.csv"
SUBSET = DATA_DIR / "ablaesse.csv"  # the vitae the workflow is tried on
GLOSSARY = DATA_DIR / "glossary.csv"
DIOCESES = DATA_DIR / "dioceses.csv"

BASE_URL = "https://chat-ai.academiccloud.de/v1"
MODEL = "gemma-4-31b-it"
MAX_ATTEMPTS = 5  # parse attempts per vita before it is left unexpanded
CHECKPOINT_EVERY = 10

RG_COLUMNS = ["volume", "nr_RG", "nr_suffix", "header_no_tags", "regest_no_tags", "id_RG_all"]


# --------------------------------------------------------------------------
# the prompts
# --------------------------------------------------------------------------

CANDIDATES_PROMPT = """**Role:** You are a historian specializing in medieval church history with expert knowledge of the Latin abbreviations used in the papal registers.

**Task:** You will receive a Latin text in which some abbreviations are marked as `[[id|abbreviation]]`, together with a list of expansion candidates for each id. For every id, select the candidate that best fits the grammatical and semantic context of the surrounding text.

**Instructions:**

1. **Choices:** Choose exactly one candidate per id, from the given candidates only.

2. **Base forms:** Return the chosen candidate exactly as it is written in the candidate list. Do not inflect, alter, or extend it — the grammatical form is adjusted in a later processing step.

3. **Occurrences:** The same abbreviation can require different expansions at different places in the text; judge each occurrence in its own context. If you are unsure, prefer the expansion most commonly associated with that abbreviation in medieval Latin church documents.

4. **Output format:** Return only a single JSON object mapping every id to the chosen candidate, e.g. `{"1": "confirmatio", "2": "dominus"}`. Do not include explanations, commentary, or any other text.

**Example:**

The text (the earlier steps have already inserted their expansions in the base form, so the text around the markers is often not grammatical):

```
decanus et capitulum collegiata ecclesia sancti Blasii [[1|e. m.]] Hildesemensis diocesis ac [[2|d.]] Ludolphus rector [[3|par.]] ecclesia: de [[4|indulg.]] pro fabrica [[5|d.]] ecclesia et pro [[6|fr.]] ordo sancti Benedicti 30. [[7|iun.]] 1435 S 309 203r.
```

The candidates:

- [[1]] `e. m.`: `extra muros`
- [[2]] `d.`: `datum`, `dictus`, `dies`, `dominus`
- [[3]] `par.`: `parens`, `parentes`, `parochialis`
- [[4]] `indulg.`: `indulgentia`, `indulgere`
- [[5]] `d.`: `datum`, `dictus`, `dies`, `dominus`
- [[6]] `fr.`: `frater`
- [[7]] `iun.`: `iunior`, `iunius`

Why these choices (for your understanding only, never write any of this in your answer): `[[1]]` is a single multi-word abbreviation and has only one candidate; `[[2]]` stands before a personal name, so `dominus`, while `[[5]]` points back to a church already mentioned, so `dictus` -- the same abbreviation, decided separately in each context; `[[3]]` belongs to `ecclesia`, so the adjective; `[[4]]` follows the preposition `de`, so the noun and not the infinitive; `[[6]]` has a single candidate, but still needs to be answered; `[[7]]` stands between a day and a year, so it is the month and not `iunior`.

The whole response for this example:

{"1": "extra muros", "2": "dominus", "3": "parochialis", "4": "indulgentia", "5": "dictus", "6": "frater", "7": "iunius"}
"""

REST_PROMPT = """**Role:** You are a historian specializing in medieval church history with expert knowledge of the Latin abbreviations used in the papal registers.

**Task:** You will receive a Latin text in which some abbreviations are marked as `[[id|abbreviation]]`. These abbreviations are simply cut-off words (they have no entry in the abbreviation glossary). For every id, either give the full word or answer "SKIP".

**Instructions:**

1. **Truncation:** Every expansion must begin with exactly the letters of the abbreviation (the part before the period) and continue it. Example: `iubil.` may become `iubilei` but never `indulgentia`. Exception: a doubled final consonant marks a plural and collapses, e.g. `eccll.` → `ecclesiarum`, `diocc.` → `diocesium`.

2. **Suggestions:** For each id you get a list of words that occur unabbreviated in the same corpus and start with the same letters, most frequent first. Prefer one of them if it fits the grammatical and semantic context. The lists can be incomplete or misleading, so you may also answer with a fitting word that is not listed.

3. **Inflection:** Give the word in the grammatical form the context requires (case, number). If several suggested forms fit and you are unsure, take the most frequent one.

4. **SKIP:** Answer "SKIP" when the marked token is not actually an abbreviation (e.g. a complete word directly before a sentence-final period, or part of an archival reference) or when you cannot expand it with confidence. Keeping the abbreviation is better than guessing wrong.

5. **Output format:** Return only a single JSON object mapping every id to its expansion or "SKIP", e.g. `{"1": "iubilei", "2": "SKIP"}`. Do not include explanations, commentary, or any other text.
"""

NORMALIZE_PROMPT = """**Role:** You are a historian specializing in medieval church history with expert knowledge of the Latin used in the papal registers.

**Task:** You will receive a Latin text in which abbreviations were previously expanded to their dictionary forms, so some words are grammatically wrong in their context. These words are marked as `[[id|word]]`, together with a list of acceptable forms for each id. For every id, select the form that fits the syntax of the surrounding text.

**Instructions:**

1. **Choices:** Choose exactly one form per id, from the given forms only. If the current form already fits the context, return it unchanged. Many marked words were already correct — do not change a word unless its context requires a different case or number.

2. **Context:** Pay attention to prepositions (`de`, `in`, `pro`, `cum`, ...), numerals, agreement with adjacent nouns and adjectives, and genitive attributes. The texts are written in the telegraphic register style of the Repertorium Germanicum: dates, sums of money and archival references are interspersed with the Latin, so judge each word by its local syntactic surroundings.

3. **Occurrences:** The same word can require different forms at different places in the text; judge each occurrence in its own context.

4. **Output format:** Return only a single JSON object mapping every id to the chosen form, e.g. `{"1": "annis", "2": "ecclesia"}`. Do not include explanations, commentary, or any other text.
"""


# --------------------------------------------------------------------------
# the model call
# --------------------------------------------------------------------------

def ask(client, model: str, system_prompt: str, user_prompt: str, parse, attempts: int,
        settings: dict | None = None):
    """
    Call the model until its answer parses, then hand the answer to the caller.

    `parse` returns `(choices, details, errors)` and `choices is None` when the
    response could not be read as JSON at all -- the only case worth retrying,
    since an answer that parses but is invalid has already been reported per
    occurrence. After the last attempt the unparseable result is returned as it
    is and the caller leaves the text alone.
    """
    parsed = (None, None, [{"message": "No attempt was made"}])
    for _ in range(attempts):
        response = call_chat_ai(client, model, system_prompt, user_prompt, settings)
        parsed = parse(response["choices"][0]["message"]["content"])
        if parsed[0] is not None:
            break
    return parsed


# --------------------------------------------------------------------------
# the three steps
# --------------------------------------------------------------------------

@dataclass
class Step:
    """What tells the three passes apart: their files, their prompt, their work."""

    number: int
    stage: str  # the name the evaluation knows the stage by
    source: Path
    output: Path
    dump: Path
    prompt: str
    prepare: Callable  # (Run) -> None; fills in preview and process
    subset: bool = False  # restrict the input to data/ablaesse.csv


@dataclass
class Run:
    """One prepared step: its data, its model, and the two entry points."""

    step: Step
    model: str
    attempts: int = MAX_ATTEMPTS
    thinking: bool | None = None  # None: whatever the model does by itself
    reasoning_effort: str | None = None
    settings: dict = field(default_factory=dict)  # what those two become in the request
    client: object = None
    source: pl.DataFrame = None
    ids: pl.DataFrame = None
    state: dict = field(default_factory=dict)  # whatever the step needed to load
    preview: Callable[[int, int], dict | None] = None  # no model call
    process: Callable[[int, int], dict | None] = None  # one model call

    def vita(self, volume: int, nr_RG: int) -> pl.DataFrame:
        return self.source.filter((pl.col("volume") == volume) & (pl.col("nr_RG") == nr_RG))

    def keys(self) -> list[tuple[int, int]]:
        return [(row["volume"], row["nr_RG"]) for row in self.ids.iter_rows(named=True)]


def describe_reasoning(run: Run) -> str:
    """How the run set the model's thinking, for the report and the log line."""
    if run.thinking is None and run.reasoning_effort is None:
        return "thinking left at the model's default"
    if run.thinking is False:
        return "thinking off"
    return "thinking on" + (f", effort {run.reasoning_effort}" if run.reasoning_effort else "")


def prepare_candidates(run: Run) -> None:
    """Step 2: choose among the Auflösungen the glossary lists."""
    glossary = pl.read_csv(GLOSSARY)
    original = pl.read_csv(RG).select(RG_COLUMNS)
    run.state["glossary"] = glossary

    def preview(volume, nr_RG):
        vita = run.vita(volume, nr_RG)
        text = vita_df_to_text(vita)
        candidates = determine_candidates(vita, glossary)
        occurrences = multiple_choice.find_candidate_occurrences(text, candidates)
        if not candidates or not occurrences:
            return None
        return {
            "text": text,
            "candidates": candidates,
            "occurrences": occurrences,
            "prompt": multiple_choice.build_user_prompt(text, occurrences, candidates),
        }

    def process(volume, nr_RG):
        ahead = preview(volume, nr_RG)
        if ahead is None:
            return None
        occurrences, candidates = ahead["occurrences"], ahead["candidates"]

        def parse(content):
            choices, errors = multiple_choice.parse_choices(content, occurrences, candidates)
            return choices, None, errors

        choices, _, errors = ask(
            run.client, run.model, run.step.prompt, ahead["prompt"], parse, run.attempts,
            run.settings,
        )
        text = multiple_choice.apply_choices(ahead["text"], occurrences, choices or {})
        return {
            "text": text,
            "record": {
                "volume": volume,
                "nr_RG": nr_RG,
                "candidates": candidates,
                "choices": [
                    {"id": occurrence.id, "abbreviation": occurrence.matched,
                     "choice": (choices or {}).get(occurrence.id)}
                    for occurrence in occurrences
                ],
                "errors": errors,
                "original_text": vita_df_to_text(
                    original.filter((pl.col("volume") == volume) & (pl.col("nr_RG") == nr_RG))
                ),
                "once_expanded_text": ahead["text"],
                "twice_expanded_text": text,
            },
        }

    run.preview, run.process = preview, process


def prepare_rest(run: Run) -> None:
    """Step 3: expand what the glossary does not know, from corpus suggestions."""
    rg = pl.read_csv(RG).select(["header_no_tags", "regest_no_tags"])
    vocabulary = expand_rest.Vocabulary.from_texts(
        rg.get_column("header_no_tags").drop_nulls().to_list()
        + rg.get_column("regest_no_tags").drop_nulls().to_list()
    )
    run.state["vocabulary"] = vocabulary

    def preview(volume, nr_RG):
        text = vita_df_to_text(run.vita(volume, nr_RG))
        occurrences = expand_rest.find_remaining_occurrences(text)
        if not occurrences:
            return None
        candidates = expand_rest.mine_candidates(occurrences, vocabulary)
        return {
            "text": text,
            "candidates": candidates,
            "occurrences": occurrences,
            "prompt": expand_rest.build_user_prompt(text, occurrences, candidates),
        }

    def process(volume, nr_RG):
        ahead = preview(volume, nr_RG)
        if ahead is None:
            return None
        occurrences, candidates = ahead["occurrences"], ahead["candidates"]
        choices, details, errors = ask(
            run.client, run.model, run.step.prompt, ahead["prompt"],
            lambda content: expand_rest.parse_expansions(content, occurrences, candidates),
            run.attempts, run.settings,
        )
        text = multiple_choice.apply_choices(ahead["text"], occurrences, choices or {})
        return {
            "text": text,
            "record": {
                "volume": volume,
                "nr_RG": nr_RG,
                "candidates": candidates,
                "details": details or [],
                "errors": errors,
                "twice_expanded_text": ahead["text"],
                "thrice_expanded_text": text,
            },
        }

    run.preview, run.process = preview, process


def prepare_normalize(run: Run) -> None:
    """Step 4: put the inserted base forms into the form the context asks for."""
    glossary = pl.read_csv(GLOSSARY)
    dioceses = pl.read_csv(DIOCESES)
    entries = glossary.select("Auflösung", "Wortstamm", "Deklination").iter_rows()
    lexicon = normalize.build_lexicon(
        list(entries) + normalize.diocese_entries(dioceses.get_column("expansion").to_list())
    )
    rg = pl.read_csv(RG).select(RG_COLUMNS)
    vocabulary = expand_rest.Vocabulary.from_texts(
        rg.get_column("header_no_tags").drop_nulls().to_list()
        + rg.get_column("regest_no_tags").drop_nulls().to_list()
    )
    forms = normalize.ranked_forms(lexicon, vocabulary)
    run.state |= {"lexicon": lexicon, "vocabulary": vocabulary, "forms": forms}

    def original_text(volume, nr_RG):
        return vita_df_to_text(
            rg.filter((pl.col("volume") == volume) & (pl.col("nr_RG") == nr_RG))
        )

    def preview(volume, nr_RG):
        text = vita_df_to_text(run.vita(volume, nr_RG))
        spans = normalize.inserted_spans(original_text(volume, nr_RG), text)
        if spans is None:
            # not a pure substitution of the original: nothing may be touched
            return {"text": text, "candidates": forms, "occurrences": None, "prompt": None}
        occurrences = normalize.find_lexicon_occurrences(text, lexicon, spans)
        if not occurrences:
            return None
        return {
            "text": text,
            "candidates": forms,
            "occurrences": occurrences,
            "prompt": normalize.build_user_prompt(text, occurrences, forms),
        }

    def process(volume, nr_RG):
        ahead = preview(volume, nr_RG)
        if ahead is None:
            return None
        if ahead["occurrences"] is None:
            return {
                "text": ahead["text"],
                "record": {
                    "volume": volume,
                    "nr_RG": nr_RG,
                    "details": [],
                    "errors": [{"message": "Alignment failed: an original word does not "
                                           "reappear in the expanded text"}],
                    "thrice_expanded_text": ahead["text"],
                    "normalized_text": ahead["text"],
                },
            }
        occurrences = ahead["occurrences"]
        choices, details, errors = ask(
            run.client, run.model, run.step.prompt, ahead["prompt"],
            lambda content: normalize.parse_forms(content, occurrences, forms),
            run.attempts, run.settings,
        )
        text = multiple_choice.apply_choices(ahead["text"], occurrences, choices or {})
        return {
            "text": text,
            "record": {
                "volume": volume,
                "nr_RG": nr_RG,
                "details": details or [],
                "errors": errors,
                "thrice_expanded_text": ahead["text"],
                "normalized_text": text,
            },
        }

    run.preview, run.process = preview, process


STEPS: dict[int, Step] = {
    2: Step(2, "twice", DATA_DIR / "once_expanded.csv", DATA_DIR / "twice_expanded.csv",
            DATA_DIR / "results_candidates.json", CANDIDATES_PROMPT, prepare_candidates,
            subset=True),
    3: Step(3, "thrice", DATA_DIR / "twice_expanded.csv", DATA_DIR / "thrice_expanded.csv",
            DATA_DIR / "results_rest.json", REST_PROMPT, prepare_rest),
    4: Step(4, "normalized", DATA_DIR / "thrice_expanded.csv", DATA_DIR / "normalized.csv",
            DATA_DIR / "results_normalize.json", NORMALIZE_PROMPT, prepare_normalize),
}


def connect() -> OpenAI:
    load_dotenv()
    return OpenAI(api_key=os.environ["API_KEY"], base_url=BASE_URL)


def prepare(step: Step, model: str = MODEL, attempts: int = MAX_ATTEMPTS, client=None,
            thinking: bool | None = None, reasoning_effort: str | None = None) -> Run:
    """
    Load everything the step needs and return it ready to run.

    Reading the RG, mining the vocabulary and building the lexicon together take
    well under a minute, so nothing is cached -- a single model call costs more.

    `thinking` and `reasoning_effort` are passed to every call of this run, in
    the shape this model wants them; see `helper_functions.thinking_kwargs` for
    what they do and what leaving them out means.
    """
    source = pl.read_csv(step.source)
    if step.subset:
        source = source.join(pl.read_csv(SUBSET), on=["volume", "nr_RG"], how="inner")
    run = Run(
        step=step,
        model=model,
        attempts=attempts,
        thinking=thinking,
        reasoning_effort=reasoning_effort,
        settings=thinking_kwargs(model, thinking, reasoning_effort),
        client=client if client is not None else connect(),
        source=source,
        ids=source.select("volume", "nr_RG").unique().sort(by="*"),
    )
    step.prepare(run)
    return run


# --------------------------------------------------------------------------
# checkpoints
# --------------------------------------------------------------------------

def checkpoint_path(step: Step) -> Path:
    return CHECKPOINT_DIR / f"step{step.number}.jsonl"


def read_checkpoint(path: Path) -> dict[tuple[int, int], dict]:
    """What an earlier run already finished, keyed by vita."""
    if not path.exists():
        return {}
    done = {}
    with open(path, encoding="utf-8") as file:
        for line in file:
            if line.strip():
                entry = json.loads(line)
                done[(entry["volume"], entry["nr_RG"])] = entry
    return done


def append_checkpoint(path: Path, entries: list[dict]) -> None:
    """Append and flush, so an interruption loses at most the last batch."""
    if not entries:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as file:
        for entry in entries:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        file.flush()
        os.fsync(file.fileno())


# --------------------------------------------------------------------------
# the loop
# --------------------------------------------------------------------------

def run_batch(run: Run, done: dict, checkpoint: Path, every: int, limit: int | None) -> dict:
    """Process every vita that is not in the checkpoint yet."""
    todo = [key for key in run.keys() if key not in done]
    if limit is not None:
        todo = todo[:limit]
    print(f"step {run.step.number}: {len(run.keys())} vitae, {len(done)} already done, "
          f"{len(todo)} to do (model {run.model}, {describe_reasoning(run)})")

    buffered = []
    try:
        for number, (volume, nr_RG) in enumerate(todo, start=1):
            result = run.process(volume, nr_RG)
            entry = {
                "volume": volume,
                "nr_RG": nr_RG,
                "text": result["text"] if result else None,
                "record": result["record"] if result else None,
            }
            buffered.append(entry)
            done[(volume, nr_RG)] = entry
            errors = len(result["record"]["errors"]) if result else 0
            print(f"  [{number}/{len(todo)}] {volume}/{nr_RG}"
                  + (" -- nothing to do" if result is None else "")
                  + (f" -- {errors} error(s)" if errors else ""))
            if len(buffered) >= every:
                append_checkpoint(checkpoint, buffered)
                buffered = []
    except KeyboardInterrupt:
        append_checkpoint(checkpoint, buffered)
        raise SystemExit(
            f"\ninterrupted -- {len(done)} vitae are in {checkpoint}; "
            f"continue with `python run_step.py {run.step.number} --resume`"
        )
    append_checkpoint(checkpoint, buffered)
    return done


def assemble(run: Run, done: dict) -> tuple[pl.DataFrame, list[dict]]:
    """The output CSV and the dump, in the order of the vitae."""
    frames, results = [], []
    for volume, nr_RG in run.keys():
        entry = done[(volume, nr_RG)]
        if entry["text"] is None:  # nothing to do: the vita passes through unchanged
            frames.append(run.vita(volume, nr_RG))
        else:
            frames.append(text_to_vita_df(entry["text"], volume, nr_RG))
        if entry["record"] is not None:
            results.append(entry["record"])
    return pl.concat(frames), results


def write_outputs(run: Run, expanded: pl.DataFrame, results: list[dict]) -> None:
    """
    The CSV for the next step and the dump for the evaluation.

    The dump records the model, its thinking settings and the prompt it was
    produced with, so the evaluation and the TEI header can state where an
    expansion comes from instead of having to be told.
    """
    expanded.write_csv(run.step.output)
    dump = {
        "step": run.step.number,
        "model": run.model,
        "reasoning": run.settings or None,
        "prompt_sha1": hashlib.sha1(run.step.prompt.encode("utf-8")).hexdigest(),
        "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results": results,
    }
    with open(run.step.dump, "w", encoding="utf-8") as file:
        json.dump(dump, file, indent=2, ensure_ascii=False)
    print(f"Wrote {run.step.output} ({len(expanded)} rows) and {run.step.dump}.")


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

ABBREVIATION = r"[a-zA-Z]{2,}\."


def count_abbreviations(texts: pl.DataFrame) -> int:
    counts = texts.select(
        pl.col("header_no_tags").str.count_matches(ABBREVIATION).sum(),
        pl.col("regest_no_tags").str.count_matches(ABBREVIATION).sum(),
    )
    return sum(value for value in counts.row(0) if value is not None)


def render_report(run: Run, expanded: pl.DataFrame, results: list[dict]) -> str:
    """The counts the notebooks used to print at the end of a batch."""
    step = run.step
    lines = [
        f"# Step {step.number}: {step.stage}",
        "",
        f"Model `{run.model}` ({describe_reasoning(run)}), {len(run.keys())} vitae, "
        f"{len(results)} of them with something to do. Written "
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}.",
        "",
        f"- abbreviations in the input: {count_abbreviations(run.source)}",
        f"- abbreviations in the output: {count_abbreviations(expanded)}",
    ]

    tiers = Counter(detail["tier"] for result in results for detail in result.get("details", []))
    if tiers:
        lines += ["", "## Acceptance", "", "| tier | occurrences |", "| --- | ---: |"]
        lines += [f"| {tier} | {count} |" for tier, count in tiers.most_common()]

    chosen = Counter(
        "chosen" if choice["choice"] is not None else "left standing"
        for result in results for choice in result.get("choices", [])
    )
    if chosen:
        lines += ["", "## Choices", "", "| outcome | occurrences |", "| --- | ---: |"]
        lines += [f"| {outcome} | {count} |" for outcome, count in chosen.most_common()]

    changes = Counter(
        f"{detail['word']} -> {detail['form']}"
        for result in results for detail in result.get("details", [])
        if detail.get("tier") == "changed"
    )
    if changes:
        lines += ["", "## The most frequent changes", "",
                  "| change | occurrences |", "| --- | ---: |"]
        lines += [f"| `{change}` | {count} |" for change, count in changes.most_common(25)]

    errors = Counter(
        error["message"].split(":")[0]
        for result in results for error in result.get("errors", [])
    )
    if errors:
        lines += ["", "## Errors", "",
                  "The model's answer was rejected and the text left as it was.", "",
                  "| kind | occurrences |", "| --- | ---: |"]
        lines += [f"| {kind} | {count} |" for kind, count in errors.most_common()]

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run one of the model-driven steps 2-4.")
    parser.add_argument("step", type=int, choices=sorted(STEPS), help="which step to run")
    parser.add_argument("--model", default=MODEL, help=f"the chat model (default: {MODEL})")
    parser.add_argument("--limit", type=int, help="process at most this many vitae")
    parser.add_argument("--resume", action="store_true",
                        help="continue the run in the checkpoint instead of starting over")
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=None,
                        help="switch the model's thinking on or off "
                             "(default: leave it at the model's own default)")
    parser.add_argument("--reasoning-effort",
                        help="how much the model may think; implies --thinking. The levels "
                             f"differ per model -- {known_efforts()}")
    parser.add_argument("--attempts", type=int, default=MAX_ATTEMPTS,
                        help=f"parse attempts per vita (default: {MAX_ATTEMPTS})")
    parser.add_argument("--checkpoint-every", type=int, default=CHECKPOINT_EVERY,
                        help=f"flush after this many vitae (default: {CHECKPOINT_EVERY})")
    arguments = parser.parse_args()

    try:  # a setting this model has no way of taking, before anything is loaded
        thinking_kwargs(arguments.model, arguments.thinking, arguments.reasoning_effort)
    except ValueError as error:
        raise SystemExit(str(error))

    step = STEPS[arguments.step]
    checkpoint = checkpoint_path(step)
    if checkpoint.exists() and not arguments.resume:
        raise SystemExit(
            f"{checkpoint} holds an unfinished run. Pass --resume to continue it, "
            "or delete the file to start over."
        )
    done = read_checkpoint(checkpoint) if arguments.resume else {}

    run = prepare(step, arguments.model, arguments.attempts,
                  thinking=arguments.thinking, reasoning_effort=arguments.reasoning_effort)
    done = run_batch(run, done, checkpoint, arguments.checkpoint_every, arguments.limit)

    missing = [key for key in run.keys() if key not in done]
    if missing:
        print(f"\n{len(missing)} vitae still missing -- {step.output} and {step.dump} are "
              f"left untouched. Continue with `python run_step.py {step.number} --resume`.")
        return

    expanded, results = assemble(run, done)
    write_outputs(run, expanded, results)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    report = render_report(run, expanded, results)
    report_path = REVIEW_DIR / f"step{step.number}_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {report_path}. The run is complete; {checkpoint} can be deleted.")


if __name__ == "__main__":
    main()
