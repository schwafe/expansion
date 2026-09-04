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

**Runs.** The output of a step is not one file but one per run:
`data/runs/<run>/step<n>.csv`, where the run is named after the model and its
thinking settings unless `--run` says otherwise. `--from` takes the input from
another run, so only the step being tried has to be run again. What produced
what is in `data/runs/<run>/manifest.json`; `runs.py` holds the layout.

**Workers.** The vitae are independent, so `--workers N` has several of them in
flight at once. The threads share the process's rate limit rather than
multiplying it, and they share it by spacing their calls four seconds apart, so
that none of them ever ask together -- which is what the endpoint refuses.
Everything that writes stays in the main thread. A vita the
endpoint never answered for -- a read timeout is routine once several requests
are queued there -- is not a result: it is left out of the checkpoint and asked
for again by `--resume`, rather than being written out unexpanded. What a run
cost is recorded per vita -- answers asked for, server errors waited out, wall
clock -- and added up in the report, because a model that is slow, an endpoint
that is overloaded and a model that cannot keep to the format look the same
from the outside and want different remedies.

**Checkpoints.** A run is 150+ model calls at 15 calls a minute, so it has to
survive being interrupted. Every vita is appended to
`data/checkpoints/<run>/step<n>.jsonl` as it is finished (flushed every ten by
default); `--resume` reads that file and processes only what is missing. The
CSV and the JSON dump are written only once every vita is done -- an
interrupted run never overwrites a complete output with a partial one.

Usage:
    python run_step.py 2 --no-thinking             # the whole subset
    python run_step.py 3 --no-thinking --limit 5   # a trial run, writes no output
    python run_step.py 4 --no-thinking --resume    # continue an interrupted run
    python run_step.py 2 --model gemma-4-31b-it --no-thinking
    python run_step.py 2 --model qwen3.8-27b --reasoning-effort low
    python run_step.py 4 --model qwen3.8-27b --no-thinking --from gemma-4-31b-it
    python run_step.py 2 --no-thinking --workers 5  # five vitae in flight at once

**Thinking.** The reasoning models think by default, which on a whole vita can
take minutes per call and rarely changes the answer, since every step is a
choice from a list. `--no-thinking` turns it off, `--reasoning-effort` sets how
much of it there is, and one of the two has to be given -- the level itself
wherever there is more than one to think at, since a request that only switches
the thinking on is answered at whatever level the endpoint gives it. What a
model does when it is not told is the endpoint's to change and is published
nowhere, so a run that left it at that would not say what it did. Every
family takes these differently and ignores what it does not know without a
word, so the request is built from the table in `helper_functions.STYLES` and
anything the model cannot do is refused before the run starts -- as is a model
the endpoint does not have, whose name would otherwise cost one 404 per vita.
What a run used is recorded in the dump next to the model name.
"""

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Callable

import polars as pl
from dotenv import load_dotenv
from openai import OpenAI

from openai import APIError

import expand_rest
import multiple_choice
import normalize
import runs
from helper_functions import (
    CALLS_PER_MINUTE,
    SPACING,
    call_chat_ai,
    check_the_model,
    determine_candidates,
    known_efforts,
    text_to_vita_df,
    thinking_kwargs,
    vita_df_to_text,
)

DATA_DIR = Path("data")

RG = DATA_DIR / "RG_header_sublemma_all.csv"
SUBSET = DATA_DIR / "ablaesse.csv"  # the vitae the workflow is tried on
GLOSSARY = DATA_DIR / "glossary.csv"
DIOCESES = DATA_DIR / "dioceses.csv"

BASE_URL = "https://chat-ai.academiccloud.de/v1"
MODEL = "gemma-4-31b-it"
MAX_ATTEMPTS = 5  # parse attempts per vita before it is left unexpanded
CHECKPOINT_EVERY = 10
WORKERS = 1  # vitae in flight at once; they share the rate limit, not multiply it
MAX_FAILURES = 10  # vitae the endpoint may fail on before the batch gives up

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
        settings: dict | None = None, label: str = ""):
    """
    Call the model until its answer parses, then hand the answer to the caller.

    `parse` returns `(choices, details, errors)` and `choices is None` when the
    response could not be read as JSON at all -- the only case worth retrying,
    since an answer that parses but is invalid has already been reported per
    occurrence. After the last attempt the unparseable result is returned as it
    is and the caller leaves the text alone.

    `label` says which vita is being asked about, for the lines the waiting
    prints: with several vitae in flight they are otherwise anonymous.

    Returns what it cost as a fourth element, because a step that is slow
    because every vita takes several answers is a prompt problem, while one
    that is slow at a single answer per vita is the model or the endpoint --
    and from the outside the two look exactly the same.
    """
    parsed = (None, None, [{"message": "No attempt was made"}])
    effort = {"tries": 0, "server_retries": 0}
    for _ in range(attempts):
        response = call_chat_ai(client, model, system_prompt, user_prompt, settings,
                                label=label)
        effort["tries"] += 1
        effort["server_retries"] += response.get("retries", 0)
        parsed = parse(response["choices"][0]["message"]["content"])
        if parsed[0] is not None:
            break
    effort["readable"] = parsed[0] is not None
    return (*parsed, effort)


# --------------------------------------------------------------------------
# the three steps
# --------------------------------------------------------------------------

@dataclass
class Step:
    """What tells the three passes apart: their prompt and their work."""

    number: int
    stage: str  # the name the evaluation knows the stage by
    prompt: str
    prepare: Callable  # (Run) -> None; fills in preview and process
    subset: bool = False  # restrict the input to data/ablaesse.csv


@dataclass
class Run:
    """One prepared step: its data, its model, and the two entry points."""

    step: Step
    model: str
    name: str = ""  # the run this belongs to, `runs.slug` by default
    source_path: Path = None  # the file this step read
    inherited: dict = field(default_factory=dict)  # the chain up to this step
    attempts: int = MAX_ATTEMPTS
    workers: int = WORKERS  # vitae in flight at once
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

    @property
    def output(self) -> Path:
        return runs.output_path(self.name, self.step.number)

    @property
    def dump(self) -> Path:
        return runs.dump_path(self.name, self.step.number)


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

        choices, _, errors, effort = ask(
            run.client, run.model, run.step.prompt, ahead["prompt"], parse, run.attempts,
            run.settings, label=f"{volume}/{nr_RG}",
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
                "effort": effort,
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
        choices, details, errors, effort = ask(
            run.client, run.model, run.step.prompt, ahead["prompt"],
            lambda content: expand_rest.parse_expansions(content, occurrences, candidates),
            run.attempts, run.settings, label=f"{volume}/{nr_RG}",
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
                "effort": effort,
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
        choices, details, errors, effort = ask(
            run.client, run.model, run.step.prompt, ahead["prompt"],
            lambda content: normalize.parse_forms(content, occurrences, forms),
            run.attempts, run.settings, label=f"{volume}/{nr_RG}",
        )
        text = multiple_choice.apply_choices(ahead["text"], occurrences, choices or {})
        return {
            "text": text,
            "record": {
                "volume": volume,
                "nr_RG": nr_RG,
                "details": details or [],
                "errors": errors,
                "effort": effort,
                "thrice_expanded_text": ahead["text"],
                "normalized_text": text,
            },
        }

    run.preview, run.process = preview, process


STEPS: dict[int, Step] = {
    2: Step(2, "twice", CANDIDATES_PROMPT, prepare_candidates, subset=True),
    3: Step(3, "thrice", REST_PROMPT, prepare_rest),
    4: Step(4, "normalized", NORMALIZE_PROMPT, prepare_normalize),
}


def connect() -> OpenAI:
    load_dotenv()
    return OpenAI(api_key=os.environ["API_KEY"], base_url=BASE_URL)


def prepare(step: Step, model: str = MODEL, attempts: int = MAX_ATTEMPTS, client=None,
            thinking: bool | None = None, reasoning_effort: str | None = None,
            name: str | None = None, parent: str | None = None,
            workers: int = WORKERS) -> Run:
    """
    Load everything the step needs and return it ready to run.

    Reading the RG, mining the vocabulary and building the lexicon together take
    well under a minute, so nothing is cached -- a single model call costs more.

    `thinking` and `reasoning_effort` are passed to every call of this run, in
    the shape this model wants them; see `helper_functions.thinking_kwargs` for
    what they do and what leaving them out means.

    `name` is the run to write into, by default the one named after this model
    and its settings; `parent` the run to take the input from, by default this
    one. See `runs.py` for how the two hang together.
    """
    name = name or runs.slug(model, thinking, reasoning_effort)
    source_path, inherited = runs.resolve_input(name, step.number, parent)
    source = pl.read_csv(source_path)
    if step.subset:
        source = source.join(pl.read_csv(SUBSET), on=["volume", "nr_RG"], how="inner")
    run = Run(
        step=step,
        model=model,
        name=name,
        source_path=source_path,
        inherited=inherited,
        attempts=attempts,
        workers=workers,
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

def checkpoint_path(run_name: str, step: Step) -> Path:
    return runs.checkpoint_path(run_name, step.number)


def checkpoint_head(run: Run) -> dict:
    """What a checkpoint says about the run that started it."""
    return {"run": run.name, "step": run.step.number, "model": run.model,
            "thinking": run.thinking, "reasoning_effort": run.reasoning_effort,
            "input": str(run.source_path)}


def read_checkpoint(path: Path) -> dict[tuple[int, int], dict]:
    """What an earlier run already finished, keyed by vita."""
    return {(entry["volume"], entry["nr_RG"]): entry
            for entry in read_checkpoint_lines(path) if "volume" in entry}


def read_checkpoint_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def read_checkpoint_head(path: Path) -> dict | None:
    """The first line of a checkpoint, or None for one written before there was any."""
    lines = read_checkpoint_lines(path)
    return lines[0] if lines and "volume" not in lines[0] else None


def start_checkpoint(path: Path, head: dict) -> None:
    """Write the head of a fresh checkpoint, so a resume can check it belongs."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(json.dumps(head, ensure_ascii=False) + "\n")


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

def process_vita(run: Run, key: tuple[int, int]) -> dict:
    """
    One vita, with what it cost -- the unit of work a worker takes off the queue.

    The wall clock is measured here rather than around the model call, so the
    time a vita spends waiting for the rate limit counts too: that is what makes
    the average comparable with the 15 calls a minute the budget allows.
    """
    volume, nr_RG = key
    started = time.monotonic()
    result = run.process(volume, nr_RG)
    if result is not None:
        seconds = round(time.monotonic() - started, 1)
        result["record"].setdefault("effort", {})["seconds"] = seconds
    return {
        "volume": volume,
        "nr_RG": nr_RG,
        "text": result["text"] if result else None,
        "record": result["record"] if result else None,
    }


def run_batch(run: Run, done: dict, checkpoint: Path, every: int, limit: int | None) -> dict:
    """
    Process every vita that is not in the checkpoint yet.

    The vitae are independent -- each is one prompt built from files that are
    only read -- so `--workers` hands several of them to the endpoint at once.
    The rate limit is kept by `helper_functions.wait_for_a_slot`, which the
    threads share, so more workers use more of the same budget rather than
    multiplying it -- and since it spaces the calls instead of counting them,
    no two of them ever go out together, at the start of a run or at the edge
    of a window. Everything that writes stays in this thread: the workers only
    return their entry, and the checkpoint is appended as the results arrive.

    A vita the endpoint gave up on (after the waiting `call_chat_ai` already
    did) is not a result and is not recorded: the batch says so, carries on with
    the others, and leaves that vita to be picked up by `--resume`. Whatever
    ends the batch -- an interruption, a failure of this code, a second Ctrl+C
    while the vitae in flight are being waited for -- the answers already paid
    for are written to the checkpoint on the way out.
    """
    start_checkpoint(checkpoint, checkpoint_head(run))
    todo = [key for key in run.keys() if key not in done]
    if limit is not None:
        todo = todo[:limit]
    print(f"step {run.step.number}: {len(run.keys())} vitae, {len(done)} already done, "
          f"{len(todo)} to do (model {run.model}, {describe_reasoning(run)}"
          + (f", {run.workers} at a time, {SPACING}s between calls"
             if run.workers > 1 else "") + ")")

    buffered: list[dict] = []
    failures: list[tuple[tuple[int, int], str]] = []

    def flush() -> None:
        append_checkpoint(checkpoint, buffered)
        buffered.clear()

    pool = ThreadPoolExecutor(max_workers=run.workers)
    queue: dict = {}  # the futures in flight or waiting for a worker, by vita
    waiting = iter(todo)

    def fill() -> None:
        """
        Keep one spare vita queued per worker and no more.

        What is never submitted needs no cancelling, so a batch that stops early
        -- interrupted, or given up on -- leaves nothing behind but the handful
        of answers it is already waiting for.

        The workers may all start at once: their calls are spread out by
        `helper_functions.wait_for_a_slot`, which is where the endpoint is
        actually spoken to.
        """
        while len(queue) < run.workers + 1:
            key = next(waiting, None)
            if key is None:
                return
            queue[pool.submit(process_vita, run, key)] = key

    def harvest(future, progress: str = "") -> None:
        """
        Take in what one worker came back with, result or failure.

        A failure must not escape: it would take the whole batch with it,
        including the answers that are waiting to be written.
        """
        volume, nr_RG = queue.pop(future)
        try:
            entry = future.result()
        except APIError as error:
            failures.append(((volume, nr_RG), f"{type(error).__name__}: {error}"))
            print(f"  {progress}{volume}/{nr_RG} -- the endpoint gave up "
                  f"({type(error).__name__}); left for --resume")
            return
        done[(volume, nr_RG)] = entry
        buffered.append(entry)
        errors = len(entry["record"]["errors"]) if entry["record"] else 0
        tries = (entry["record"] or {}).get("effort", {}).get("tries", 1)
        print(f"  {progress}{volume}/{nr_RG}"
              + (" -- nothing to do" if entry["record"] is None else "")
              + (f" -- {tries} tries" if tries > 1 else "")
              + (f" -- {errors} error(s)" if errors else ""))

    interrupted = False
    number = 0
    try:
        fill()
        while queue:
            finished, _ = wait(list(queue), return_when=FIRST_COMPLETED)
            for future in finished:
                number += 1
                harvest(future, f"[{number}/{len(todo)}] ")
            if len(buffered) >= every:
                flush()
            if len(failures) >= MAX_FAILURES:
                print(f"\n{len(failures)} vitae the endpoint gave up on -- stopping "
                      "rather than working through the rest of them")
                break
            fill()
    except KeyboardInterrupt:
        interrupted = True
    finally:
        try:
            for future in queue:
                future.cancel()
            outstanding = [future for future in queue if not future.cancelled()]
            if interrupted and outstanding:
                # they are answered or being answered, so they are kept and go
                # on counting; what had not started is what is dropped
                print(f"\ninterrupted -- {len(outstanding)} vitae are answered or in "
                      "flight; waiting for them, they count too")
            pool.shutdown(wait=True)
            for future in list(queue):
                if future.done() and not future.cancelled():
                    number += 1
                    harvest(future, f"[{number}/{len(todo)}] ")
        finally:  # a second Ctrl+C must not cost the answers already paid for
            flush()

    if interrupted:
        raise SystemExit(
            f"\ninterrupted -- {len(done)} vitae are in {checkpoint}; "
            f"continue with `python run_step.py {run.step.number} "
            f"--run {run.name} --resume`"
        )
    if failures:
        print(f"\n{len(failures)} vitae the endpoint did not answer for; they are not "
              f"in {checkpoint} and a resume will ask for them again:")
        for (volume, nr_RG), why in failures:
            print(f"  {volume}/{nr_RG}: {why}")
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
    produced with, and the manifest records the same next to the file this step
    read -- so the evaluation and the TEI header can state where an expansion
    comes from, through however many runs the chain reaches back.
    """
    run.output.parent.mkdir(parents=True, exist_ok=True)
    expanded.write_csv(run.output)
    written = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prompt_sha1 = hashlib.sha1(run.step.prompt.encode("utf-8")).hexdigest()
    dump = {
        "step": run.step.number,
        "run": run.name,
        "model": run.model,
        "reasoning": run.settings or None,
        "prompt_sha1": prompt_sha1,
        "input": str(run.source_path),
        "written": written,
        "results": results,
    }
    with open(run.dump, "w", encoding="utf-8") as file:
        json.dump(dump, file, indent=2, ensure_ascii=False)
    runs.record(
        run.name, run.step.number, run.inherited,
        model=run.model,
        thinking=run.thinking,
        reasoning_effort=run.reasoning_effort,
        prompt_sha1=prompt_sha1,
        input=str(run.source_path),
        output=str(run.output),
        dump=str(run.dump),
        vitae=len(run.keys()),
        written=written,
    )
    print(f"Wrote {run.output} ({len(expanded)} rows), {run.dump} "
          f"and {runs.manifest_path(run.name)}.")


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


def effort_section(run: Run, results: list[dict]) -> list[str]:
    """
    What the run cost: answers per vita, seconds per answer, and what that is
    in calls a minute against the budget.

    A step can be slow for three reasons that look identical from the outside --
    the model is slow, the endpoint is overloaded, or the model keeps answering
    in a shape that cannot be read and every vita costs several answers. The
    three are separated here, because the fix differs: wait, add workers, or
    mend the prompt.
    """
    efforts = [result["effort"] for result in results if result.get("effort")]
    if not efforts:
        return []
    tries = [effort["tries"] for effort in efforts]
    seconds = [effort["seconds"] for effort in efforts if effort.get("seconds") is not None]
    retried = [count for count in tries if count > 1]
    unreadable = sum(1 for effort in efforts if not effort.get("readable", True))
    waited_out = sum(effort.get("server_retries", 0) for effort in efforts)

    rows = [
        ("vitae the model answered for", str(len(efforts))),
        ("answers", f"{sum(tries)}, {sum(tries) / len(tries):.2f} per vita"),
    ]
    if retried:
        rows.append(("vitae that took more than one",
                     f"{len(retried)}, at worst {max(retried)} answers"))
    if unreadable:
        rows.append(("vitae with no readable answer at all", str(unreadable)))
    if seconds:
        rows.append(("seconds per vita", f"{mean(seconds):.1f} on average, "
                                         f"{median(seconds):.1f} median, "
                                         f"{max(seconds):.1f} at worst"))
        per_answer = sum(seconds) / sum(tries)
        rows.append(("seconds per answer", f"{per_answer:.1f}"))
        rows.append(("answers a minute", f"about {60 / per_answer * run.workers:.1f} at "
                                         f"{run.workers} vita(e) at a time, of the "
                                         f"{CALLS_PER_MINUTE} the rate limit allows"))
    if waited_out:
        rows.append(("server errors waited out", str(waited_out)))

    return (["", "## Effort", "",
             "What the run cost. A vita takes a second answer only when the model's "
             "reply cannot be read as JSON at all, so several answers per vita is a "
             "matter for the prompt, while a long time at one answer per vita is the "
             "model or the endpoint.", "",
             "| | |", "| --- | --- |"]
            + [f"| {what} | {value} |" for what, value in rows])


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
    lines += effort_section(run, results)

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

def warn_about_the_prompt(name: str, step: Step) -> None:
    """
    Say so when this run's last output for the step came from another prompt.

    The run is named after the model and its settings, so a prompt that has been
    edited since would otherwise replace a result of different instructions with
    no trace of it.
    """
    before = runs.previous_prompt(name, step.number)
    now = hashlib.sha1(step.prompt.encode("utf-8")).hexdigest()
    if before is not None and before != now:
        print(f"note: {name} step {step.number} was last written with prompt {before[:8]}, "
              f"this one is {now[:8]} -- the output will be replaced")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one of the model-driven steps 2-4.")
    parser.add_argument("step", type=int, choices=sorted(STEPS), help="which step to run")
    parser.add_argument("--model", default=MODEL, help=f"the chat model (default: {MODEL})")
    parser.add_argument("--limit", type=int, help="process at most this many vitae")
    parser.add_argument("--resume", action="store_true",
                        help="continue the run in the checkpoint instead of starting over")
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=None,
                        help="switch the model's thinking on or off; one of this and "
                             "--reasoning-effort is required, so that what a run did is "
                             "recorded rather than left to the model. Where the model has "
                             "levels, --thinking alone does not say enough")
    parser.add_argument("--reasoning-effort",
                        help="how much the model may think; implies --thinking, and stands "
                             "in for it. The levels differ per model -- "
                             f"{known_efforts()}")
    parser.add_argument("--run", help="the run to write into (default: the model and its "
                                      "settings, e.g. gemma-4-31b-it-nothink)")
    parser.add_argument("--from", dest="parent",
                        help="the run to take the input of this step from (default: this run)")
    parser.add_argument("--attempts", type=int, default=MAX_ATTEMPTS,
                        help=f"parse attempts per vita (default: {MAX_ATTEMPTS})")
    parser.add_argument("--checkpoint-every", type=int, default=CHECKPOINT_EVERY,
                        help=f"flush after this many vitae (default: {CHECKPOINT_EVERY})")
    parser.add_argument("--workers", type=int, default=WORKERS,
                        help="how many vitae to have in flight at once; they share the "
                             f"rate limit of {CALLS_PER_MINUTE} calls a minute "
                             f"(default: {WORKERS})")
    arguments = parser.parse_args()
    if arguments.workers < 1:
        raise SystemExit("--workers takes at least 1")
    if arguments.thinking is None and arguments.reasoning_effort is None:
        # what the model does when it is not told is nowhere in the run: the
        # deployment may change it between two runs and both would read alike
        raise SystemExit(
            "say what the model is to do with its thinking: --no-thinking, --thinking or "
            f"--reasoning-effort ({known_efforts()}). Left at the model's own default it "
            "is not recorded anywhere and can change under the run."
        )

    client = connect()
    try:  # what this model is not, and what it cannot do, before anything is loaded
        check_the_model(client, arguments.model)  # first: a typo has no thinking style either
        thinking_kwargs(arguments.model, arguments.thinking, arguments.reasoning_effort)
    except ValueError as error:
        raise SystemExit(str(error))

    step = STEPS[arguments.step]
    name = arguments.run or runs.slug(arguments.model, arguments.thinking,
                                      arguments.reasoning_effort)
    checkpoint = checkpoint_path(name, step)
    if checkpoint.exists() and not arguments.resume:
        raise SystemExit(
            f"{checkpoint} holds an unfinished run. Pass --resume to continue it, "
            "or delete the file to start over."
        )
    done = read_checkpoint(checkpoint) if arguments.resume else {}
    warn_about_the_prompt(name, step)

    try:  # nothing to build this step on: the message says what is there
        run = prepare(step, arguments.model, arguments.attempts, client=client,
                      thinking=arguments.thinking,
                      reasoning_effort=arguments.reasoning_effort,
                      name=name, parent=arguments.parent,
                      workers=arguments.workers)
    except (LookupError, ValueError) as error:
        raise SystemExit(str(error))

    head = read_checkpoint_head(checkpoint)
    if head is not None and head != checkpoint_head(run):
        raise SystemExit(
            f"{checkpoint} was written by {head} but this is {checkpoint_head(run)}. "
            "Resume it as it was, or delete the file to start over."
        )
    done = run_batch(run, done, checkpoint, arguments.checkpoint_every, arguments.limit)

    missing = [key for key in run.keys() if key not in done]
    if missing:
        print(f"\n{len(missing)} vitae still missing -- {run.output} and {run.dump} are "
              f"left untouched. Continue with "
              f"`python run_step.py {step.number} --run {name} --resume`.")
        return

    expanded, results = assemble(run, done)
    write_outputs(run, expanded, results)
    report = render_report(run, expanded, results)
    report_path = runs.report_path(name, step.number)
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {report_path}. The run is complete; {checkpoint} can be deleted.")


if __name__ == "__main__":
    main()
