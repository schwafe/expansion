# Workflow

0. Extract the information from the glossary into a structured format (csv), storing information systematically - extract_glossary.py (includes cleaning the morphology columns via clean_morphology.py)
1. Expand abbreviations in the text using the glossary information, where a simple rule suffices - expand_simple.py
2. For abbreviations where there are multiple candidates, let an LLM choose the most likely - run_step.py 2
3. For abbreviations where there are no candidates in the glossary, mine candidates from the RG and suggest these, but let an LLM choose freely - run_step.py 3
4. Let an LLM normalise the text (e.g. fix inflection, spelling, punctuation, etc.) - run_step.py 4
5. Measure the result against the gold labels, so a change to the workflow can be judged by a number - evaluate.py
6. Write the result as a TEI document that holds both the text of the RG and the expansion - to_tei.py

# Step 0: extracting the glossary
`extract_glossary.py` builds `data/glossary.csv` from `data/RGAbkVerz.csv` (the raw export of the Abkürzungsverzeichnis, the source of truth — it is never hand-edited).

```bash
python extract_glossary.py --write
```

Without `--write` it is a dry run that prints the report; `--diff-old` additionally compares the result with the CSVs currently on disk (`data/review/diff_*.csv`), so a re-extraction can be reviewed before it is written.

Every manual decision is an explicit, documented entry in the `CORRECTIONS`/`ADDITIONS` tables of the script rather than an edit in the data — each carries the reason for it, and a correction that no longer matches any row aborts the run, so the tables cannot silently go stale if the export is updated. The remaining stages are documented in the module docstring; in short: continuation rows inherit their abbreviation, the Auflösung is normalised (alternative expansions become separate rows, notation like `op(p)idum` or `subcustos/succustos` is resolved against the abbreviation, and where the abbreviation fits both spellings the more frequent one in the RG wins), the `RG1`–`RG9` columns are reduced to the row's own abbreviation (variants they name become their own rows), abbreviations that never occur in the RG are dropped, and what is left is marked `komplex` or not. Finally `clean_morphology.py` cleans the Wortstamm/Deklination columns (see below).

Every run writes `data/review/`:
- `extraction_report.md` — the log of the run: all counts, every applied correction with its reason, and every flagged row. This is the documentation of the extraction.
- `morphology_review.csv` — rows whose Wortstamm/Deklination could not be cleaned automatically (they keep their original values).
- `morphology_unattested.csv` — entries whose generated paradigm has no form at all in the RG (a hint at a wrong stem or declension class).
- `aufloesung_unattested.csv` — Auflösung words that never occur written out in the RG.
- `rg_volume_mismatch.csv` — rows claiming a volume in which the abbreviation is not actually found.

The last three are quality checks against the corpus, not errors: they are the list of entries worth a manual look.

The `komplex` column is the one thing in `glossary.csv` that is not in the Abkürzungsverzeichnis: it says whether step 1 may expand the entry by rule (`false`) or whether the reading has to be decided occurrence by occurrence in step 2 (`true`). An abbreviation is always wholly one or the other — if any of its rows is ambiguous, all of them are, since step 1 could otherwise expand one reading and leave its siblings standing. Note that the two kinds are cleaned slightly differently: the Auflösung of a complex entry is a candidate text for the model, so the glossary's notes have been moved out of it into `Anmerkungen`, and rows that this made identical were merged.

# Step 1: expansion by rule
`expand_simple.py` expands what needs no judgement: an abbreviation for which the volume at hand knows exactly one Auflösung. This is the only step that runs over the whole RG rather than over the test subset.

```bash
python expand_simple.py            # dry run, prints the report
python expand_simple.py --write    # write data/step1.csv
```

Where a volume lists several Auflösungen for the same abbreviation, nothing is substituted — that is what step 2 decides, one occurrence at a time. Two decisions in this step are not forced by the data and are worth stating:

- **Volume columns.** A row whose `RG1`–`RG9` columns are all empty and whose abbreviation appears nowhere else in the glossary is read as applying to every volume. The glossary simply does not record a volume for those entries, and since no other row claims the abbreviation, no reading can be lost by it. A row that is empty *and* has siblings is left alone: there the volume columns are precisely what tells the readings apart.
- **Volume 10.** The glossary has no rules for it, so it is dropped here and never reaches the later steps.

The substitution uses `multiple_choice.occurrence_pattern`, the same pattern step 2 marks its occurrences with, so both steps agree on where an abbreviation begins and ends — in particular on the optional spaces inside a multi-word abbreviation (`e. m.` and `e.m.`). Longer abbreviations are applied first, so `s. p. d.` is resolved as a whole and never as three separate parts. No expansion contains a period and every abbreviation ends in one, so an expansion can never be expanded again.

`--write` produces `data/step1.csv` and `data/review/expansion_report.md` — how many abbreviations the substitution resolved, how many rules each volume could apply, the most frequent abbreviations before and after, and what a clearer glossary entry would gain (the abbreviations still standing although the glossary knows them, ranked by how often they occur).

# Steps 2–4: the model-driven passes
The three passes differ only in what they ask the model and what they let it answer. The loop around them is the same and lives in `run_step.py`: read the output of the previous step, take one vita at a time, mark the occurrences in the text, ask the model, substitute its answer programmatically, record what happened.

```bash
python run_step.py 2 --no-thinking              # the whole subset
python run_step.py 3 --no-thinking --limit 5    # a trial run, writes no output
python run_step.py 4 --no-thinking --resume     # continue an interrupted run
python run_step.py 2 --model qwen3.8-27b --reasoning-effort low
python run_step.py 4 --model qwen3.8-27b --no-thinking --from gemma-4-31b-it   # only step 4 anew
python run_step.py 2 --no-thinking --workers 5  # five vitae in flight at once
```

**Runs.** A step is worth running with several models, and the interesting comparisons mix them — one model for the choices, another for the grammar — so the output of a step is not one file but one per run:

```
data/step1.csv                       the rule-based expansion, the same for every run
data/runs/gemma-4-31b-it/
    manifest.json                    what produced every step of this chain
    step2.csv  step2.json  step2_report.md
    step3.csv  step3.json  step3_report.md
    step4.csv  step4.json  step4_report.md
data/runs/qwen3.8-27b-nothink/
    manifest.json                    steps 2–3 inherited from gemma-4-31b-it
    step4.csv  step4.json  step4_report.md
```

A run is named after the model and its thinking settings (`gemma-4-31b-it`, `qwen3.8-27b-nothink`, `deepseek-v4-flash-0731-low`), so running the whole workflow with one model needs no extra flag; `--run NAME` overrides the name for a chain worth labelling. A step reads the output of the step before it **in its own run**, unless `--from RUN` points it at another one — then that run's manifest entries come along, so every manifest describes a complete chain from step 1 onwards no matter how many runs it reaches back through. A step with nothing to build on says so and lists the runs that have what it needs, rather than falling back to whatever file was there last:

```
$ python run_step.py 4 --model qwen3.8-27b --no-thinking
run 'qwen3.8-27b-nothink' has no step 3 to build on. Pass --from <run>; these have one: gemma-4-31b-it
```

The layout lives in `runs.py`, which is what `run_step.py`, `evaluate.py` and `to_tei.py` ask for a path. Because a run is named after the model and its settings, a re-run replaces its own output — so a prompt that has been edited since is announced (`the output will be replaced`) instead of quietly overwriting a result that came from different instructions.

**The model never rewrites the text.** Each occurrence is marked as `[[id|abbreviation]]` and the model returns only a JSON object mapping id to its answer; the substitution happens in code. That replaced an earlier full-text rewrite which corrupted words it should not have touched (`Halberstad.` → `Halhalstad.`), silently expanded abbreviations it had no business expanding, and needed a fragile token diff to validate. Everything the model may change is decided before the call and checked after it, so a bad answer can only leave the text as it was: step 2 accepts only a candidate from the list it offered, step 3 only an expansion that continues the letters of the abbreviation, step 4 only a form from the word's own paradigm.

**Thinking.** The reasoning models think by default, which on a whole vita can take minutes per call — and there is not much for them to reason about, since every step is a choice from a list the code has already narrowed down. `--no-thinking` turns it off, `--reasoning-effort` sets how much of it there is (and turns it on by itself), and **one of the two has to be given**: what a model does when it is not told is written down nowhere, and the deployment may change it between two runs that would then read alike. What a run used is recorded in the dump and the report next to the model name, so a run can be told apart from one with the same model and a different setting.

The price of that is that a model with no entry in the table below cannot be run until it gets one — which is the point: the entry is what makes the setting arrive in the shape that model understands.

Every family wants this asked differently, and **ignores what it does not know without a word**: the settings are mostly not API parameters but variables of the model's chat template (`extra_body={"chat_template_kwargs": ...}`), and a template that does not use the variable renders exactly the prompt it would have rendered anyway — the request is valid, the model answers as usual, and nothing in the response says the setting was dropped. `helper_functions.STYLES` therefore holds one entry per family, taken from the model cards:

| model | thinking on and off | how much |
| --- | --- | --- |
| `gemma-4*`, `glm-4*`, `qwen3*` | `enable_thinking` in the template | — |
| `qwen3.8*` | `enable_thinking` in the template | `reasoning_effort` parameter: `low`, `medium`, `xhigh` |
| `deepseek-v4*` | `thinking` in the template | `reasoning_effort` in the template: `low`, `high`, `max` |
| `mistral-medium-3.5*` | through the level alone | `reasoning_effort` parameter: `none`, `high` |
| `openai-gpt-oss*` | always reasons | `reasoning_effort` parameter: `low`, `medium`, `high` |
| `apertus*`, `meta-llama-3.1*`, `devstral*` | does not think at all | — |

`thinking_kwargs(model, ...)` builds the request from that table and refuses before the run starts what a model has no way of taking — a level it does not know, `--no-thinking` for a model that always reasons, `--thinking` for one that does not think, a model with no entry at all. So a setting is either sent in the shape that model understands or reported; it is never quietly dropped.

**A level is not optional where there is one.** `--thinking` alone is enough for a family whose table row has no levels (`gemma-4*`, `glm-4*`, `qwen3*`) and for one whose switch *is* the level (`mistral-medium-3.5*`, where thinking on means `high`), and it is refused for `qwen3.8*` and `deepseek-v4*`: told only to think, they think as much as they like, which is the deployment's to change and would appear in no report. The models that do not think at all take `--no-thinking` — true of them whatever is sent — and refuse the rest.

The entries were checked against the endpoint by asking one small arithmetic question per model and setting and counting the completion tokens, which is the only reliable signal — the wall clock says nothing, since the same request can take 0.1s or 90s depending on the load. Thinking off against on: `gemma-4-31b-it` 4 → 225 tokens, `qwen3.8-27b` 4 → 50, `deepseek-v4-flash-0731` 2 → 49, `mistral-medium-3.5-128b` 4 (`none`) → 152 (`high`), `openai-gpt-oss-120b` 20 (`low`) → 45 (`medium`) → 84 (`high`). Only `glm-4.7` answers with the same 3 tokens whatever it is asked, so that deployment seems to have its thinking switched off for good. The levels are worth less than the switch: on deepseek and on qwen3.8 they differ from each other only within the noise of a question this small.

The three that do not think were measured the same way and are in the table for the same reason — a model missing from it cannot be run at all, and these are perfectly usable otherwise. `apertus-70b-instruct-2509` answers with the same 3 tokens and no `reasoning_content` whether it is sent `enable_thinking`, a `reasoning_effort` or nothing: it accepts every setting and ignores all of them. `meta-llama-3.1-8b-instruct` likewise (its answers vary, but the same setting gives both lengths, so the variation is noise and not thought). `devstral-2-123b-instruct-2512` refuses template variables outright (`chat_template is not supported for Mistral tokenizers`) and takes `reasoning_effort` only as `none` or `high`, like the other Mistral — but unlike it answers the identical 179 tokens to both, so the parameter is accepted and does nothing.

**The model's name.** It is checked against the list the endpoint publishes before anything is loaded, because a name the endpoint does not know is not refused once but once per vita — every one of them is answered with a 404 and left for `--resume`, which reads like a bad day at the endpoint rather than like a typo. The list is short enough to print, and the name that was meant is usually in it:

```
$ python run_step.py 2 --model gpt-oss-120b123123 --no-thinking
https://chat-ai.academiccloud.de/v1/ has no model 'gpt-oss-120b123123'. It has:
  apertus-70b-instruct-2509
  deepseek-v4-flash-0731
  ...
  openai-gpt-oss-120b
```

An endpoint that cannot be reached at all only prints a note: that says nothing about the model, and the vitae are asked for over the next hour anyway.

**Checkpoints.** A run is 150+ model calls at 15 calls a minute, so it has to survive being interrupted. Every vita is appended to `data/checkpoints/<run>/step<n>.jsonl` as it is finished (flushed every ten by default, `--checkpoint-every` to change it), and `--resume` processes only what is missing. The first line records the run, the model and its settings, so a resume with anything else is refused rather than interleaved into one file. The CSV and the JSON dump are written only once every vita is done, so an interrupted or `--limit`ed run never overwrites a complete output with a partial one.

**Workers.** The vitae are independent — each is one prompt built from files that are only read — so `--workers N` hands several of them to the endpoint at once, starting them `STAGGER` (0.5s) apart. Fifteen calls arriving together is what the endpoint refuses — a burst of 429s that then retry together, in waves — while the same fifteen spread over seven seconds go through; only the first call of each worker is held back, since from then on they are spread out by the answers they are waiting for. The rate limiter is shared by the threads of the process (`ratelimit` holds a lock), so more workers use more of the same 15 calls a minute rather than multiplying the budget; everything that writes stays in the main thread, which only collects what the workers return. A model that answers in a minute leaves 14 of the 15 calls unused, and five workers turn that into five. Only one spare vita per worker is ever queued, so a batch that stops early leaves nothing behind but the handful of answers it is already waiting for; on Ctrl+C those are finished and checkpointed — they are paid for — and a second Ctrl+C while they finish still writes them.

**When the endpoint gives up.** With several vitae in flight the endpoint queues them, and a request that never comes back (`APITimeoutError`) says the queue was long, not that this vita is unanswerable — so it is waited out like a 500 or a 429, with the wait growing each time (5s, 10s, 15s …) since all three mean the endpoint has more work than it can take. The wait is jittered by ±25%, because requests refused in the same instant would otherwise wait the same time and arrive in the same instant again, in waves. A vita it still refuses to answer for is **not a result**: it is left out of the checkpoint, named at the end of the batch, and asked for again by `--resume`, while the rest of the batch carries on. It is never recorded as an empty answer, which would write the vita out unexpanded and never ask about it again. If ten vitae fail the batch stops rather than working through the rest of them.

**Was it slow, or was it the prompt?** A step can be slow for three reasons that look identical from the outside: the model is slow, the endpoint is overloaded, or the model keeps answering in a shape that cannot be read, so every vita costs several answers. Each vita therefore records what it cost — how many answers it took, how many server errors were waited out inside them, and its wall clock — and `step<n>_report.md` adds them up:

```
## Effort
| | |
| --- | --- |
| vitae the model answered for | 154 |
| answers | 166, 1.08 per vita |
| vitae that took more than one | 11, at worst 4 answers |
| seconds per vita | 62.4 on average, 58.0 median, 180.2 at worst |
| seconds per answer | 57.8 |
| answers a minute | about 1.0 at 1 vita(e) at a time, of the 15 the rate limit allows |
| server errors waited out | 3 |
```

More than one answer per vita is a matter for the prompt; a long time at one answer per vita is the model or the endpoint, and that is what `--workers` is for.

**What a run leaves behind.** In `data/runs/<run>/`: the CSV for the next step, a dump of every decision (`step<n>.json`) that also records the model, its thinking settings, the prompt and the file the step read — so the evaluation and the TEI header can state where an expansion comes from instead of having to be told — `step<n>_report.md` with the acceptance tiers, the errors and the most frequent changes, and the manifest tying the chain together.

**Trying something by hand.** `expanding_candidates.ipynb`, `expanding_rest.ipynb` and `normalizing.ipynb` are probes: they import from `run_step.py` and run a single vita, showing the text, the candidates, the whole prompt, the result and every decision. What is tried there is exactly what the batch does, and `prepare(STEPS[2], model=..., thinking=..., reasoning_effort=...)` switches the model and its thinking for the experiment.

## Step 2: choosing among the glossary candidates
The candidates for an abbreviation are the Auflösungen the glossary lists for it in this volume (`helper_functions.determine_candidates`), so this step only ever sees the abbreviations that have more than one reading — the genuinely ambiguous ones. The chosen candidate is inserted in its base (dictionary) form; the inflection is left to step 4. Because the answer must be a member of the candidate list, validating it is a membership test, and an invalid answer simply leaves the abbreviation standing.

## Step 3: expanding what the glossary does not know
What is left after steps 1 and 2 are the abbreviations **without a glossary entry** — mostly truncated words like `iubil.` or `procur.` and diocese adjectives that slipped through. There is no curated candidate list for them, so two other safeguards replace the membership test (`expand_rest.py`):

1. **Corpus-mined suggestions**: words that appear *unabbreviated* somewhere in the RG and share the abbreviation's prefix are offered to the model, ranked by frequency. They are real surface forms from the same corpus, so the model can usually pick an already correctly inflected word instead of inventing one.
2. **Truncation constraint**: these abbreviations are cut-off words, so any expansion — suggested or free — must begin with the letters of the abbreviation itself. A doubled final consonant (`eccll.`, `diocc.`) marks a plural and is allowed to collapse (`eccll.` → `ecclesiarum`). Expansions that violate the constraint are rejected and the abbreviation is kept.

The model may also answer `"SKIP"` for tokens that are not really abbreviations (a word before a sentence-final period, part of an archival reference) or that it cannot expand confidently — keeping an abbreviation is always better than a wrong expansion. Every response is recorded with its acceptance tier (`suggestion` / `free` / `skip` / `rejected` / `missing`).

## Step 4: normalizing the grammar
Steps 1 and 2 insert the glossary expansions in their base form, so the expanded text contains words that are grammatically wrong in their context (`de 7 annus` instead of `de 7 annis`). This step inflects them, again as a multiple choice (`normalize.py`):

- Words that were never abbreviated must not change at all. The expansion steps only ever replace abbreviations, so every original word reappears unchanged and in order in the expanded text; aligning the two texts (`inserted_spans`) identifies the words the pipeline inserted. An original word that is indistinguishable from an adjacent identical insertion counts as inserted too, so it can still be normalized. If an original word does *not* reappear, the expanded text was not produced by pure substitution — the vita is then flagged and left untouched.
- Of the inserted words, those that **are a glossary base form** are marked as `[[id|word]]`; words still followed by a period are unexpanded abbreviations and are skipped as well.
- The candidate list for each id is the word's **full paradigm**, generated by `paradigm.py` from the cleaned Wortstamm/Deklination columns and ranked by how often each form actually occurs in the RG. The diocese adjectives from `dioceses.csv` (which have no morphology columns) are added as regular i- and o/a-declension adjectives.
- The model returns the fitting form — or the current one to keep it. Every choice is validated against the paradigm, so the model can fix the inflection but can never change the word or corrupt the text.

Every response is recorded with a tier (`changed` / `kept` / `rejected` / `missing`).

## Which models were tried
Judged by hand on the chat-ai.academiccloud.de endpoint, most of them before the multiple-choice reformulation — back then the model rewrote the whole text, so several of the complaints below are about it changing what it should not have, which the current setup makes impossible. `--model` switches the model for a run.

The reasoning models among them are worth a second try with `--no-thinking` or a low effort: the earlier verdicts were reached with the thinking they do by default, which the multiple-choice reformulation has made largely pointless.

| model | verdict |
| --- | --- |
| `gemma-4-31b-it` | decent — the default. Does not expand what it should not, but hallucinates where there is nothing to expand (expanded `A` without a period), which is worth catching anyway. Adjusted an expansion on its own initiative (used the Auflösung `(gratia ) expectativa` as just `expectativa`) — that can be good, but it can also introduce errors. `Tru[d]perti` became `Trudperti`. |
| `openai-gpt-oss-120b` | decent |
| `glm-4.7` | decent? |
| `deepseek-r1-distill-llama-70b` | bad |
| `apertus-70b-instruct-2509` | terrible |
| `mistral-large-3-675b-instruct-2512` | terrible? — did not respect the scope instruction of the prompt |
| `qwen3.5-397b-a17b` | terrible? — a huge amount of reasoning for a bad result (only tried on one example) |

Latin-specific models, tried with a plain "Please expand all abbreviations in the following text":

- `mschonhardt/latin-normalizer` — terrible for expanding: leaves things out and hallucinates. Might still be useful for the normalisation of step 4.
- `andbue/byt5-base-latin-normalize` — useless for expanding.
- `dantedgp/latin-english-MT` — completely useless.
- `hathibelagal/llama-3.2-latin` — seemed promising, but that prompt for some reason led to no output being generated at all.

# Step 5: quality control
`evaluate.py` scores the output of every stage against the gold expansions in `data/to_compare_with/fable_expanded.csv`.

```bash
python evaluate.py                        # the only run there is, or --run says which
python evaluate.py --run qwen3.8-27b-low
python evaluate.py --write                # also write data/runs/<run>/evaluation_*
python evaluate.py --save-baseline        # store the current numbers as this run's baseline
python evaluate.py --baseline             # print the change against that baseline
python evaluate.py --runs                 # every run in one table, into data/review/runs.md
```

**Which run.** The stages come from the run's manifest, so a chain that borrowed its step 3 from another run is scored against the files that actually produced it, and the report opens with a table saying which model did which step and when. A run that has only reached step 2 is scored as far as step 2 rather than left out, so a new model can be judged before the rest is re-run. With one run present none of this has to be said; with several, `--run` does, because guessing would score the wrong model's output.

Each run keeps its own `evaluation_report.md`, `evaluation_mismatches.csv`, `evaluation_by_abbreviation.csv` and `evaluation_baseline.json` in its directory — a baseline belongs to a run, since it answers whether *this* chain got better. `--runs` puts them side by side in `data/review/runs.md`, sorted by form accuracy, with the model of each step and the stage each run was scored at:

| run | step 2 | step 3 | step 4 | scored at | word accuracy | form accuracy |
| --- | --- | --- | --- | --- | ---: | ---: |
| `gemma-4-31b-it` | `gemma-4-31b-it (default)` | `gemma-4-31b-it (default)` | `gemma-4-31b-it (default)` | step 4 (normalized) | 92.9% | 64.8% |

The unit of measurement is the single abbreviation, not the text: a text-level diff mixes one expansion error with twenty inflection differences and tells you nothing actionable. The abbreviated source text is the anchor — for each vita it is aligned with the gold and with each stage output at word level, so every abbreviation gets a gold expansion and a system expansion that are compared directly. The alignment works because the expansion steps only ever replace abbreviations, so every word that was not abbreviated reappears unchanged and anchors the alignment (the property `normalize.py` already relies on); inside a changed passage each abbreviation is re-anchored on the expansion that continues it (`eccl.` → `ecclesiam`, or via the glossary where it does not, `aep.` → `archiepiscopus`). What cannot be anchored is reported as `unaligned` and left out of every rate rather than scored — that number is the reliability check on the metric itself.

Two rates are reported per stage, because a single exact-match number would score `thrice_expanded` (deliberately base forms) as broken:
- **word accuracy** — was the right word chosen? This is what steps 1–3 do; it should rise from step 1 to step 3 and stay flat at step 4, which cannot change a word.
- **form accuracy** — is the text right as it stands? This is what step 4 has to move.

Two expansions count as the same form when their spelling variants agree (`ecclesiae`/`ecclesie`, `opidum`/`oppidum`, `parochialis`/`parrochialis`), and as the same word when the glossary paradigms say so (`paradigm.entry_forms`, the same forms step 4 may choose from); for words the glossary has no morphology for (step 3 mines them from the corpus) a shared stem plus a real case ending stands in, reported as `wrong form?` so the uncertainty stays visible. Abbreviations the gold itself leaves standing (`etc.`, month names, place initials) get `no_gold_label` and are excluded — the pipeline may well have expanded them correctly, there is just nothing to compare against.

Every occurrence is also attributed to the step that produced its expansion, by comparing the four stage texts, so a wrong word can be traced to a wrong rule (step 1), a bad candidate choice (step 2) or a bad corpus suggestion (step 3).

Steps 2 and 3 do not invent an expansion, they choose one from a list, so a wrong word is only the model's fault if the list held the right one. The candidate lists are read back from the dumps the two steps wrote (`data/runs/<run>/step2.json`, `step3.json`) — an entry counts only if the text it records is exactly the stage text being scored, so a dump left over from an earlier run cannot be counted against the current one. Each error is then split into a **candidate miss** (no offered candidate would have scored as the right word, whatever the model had picked) and a choice error, which gives the report a **ceiling** — the accuracy the step could have reached — and a **choice accuracy** over exactly the occurrences it could have got right. Step 3 may also expand freely as long as the expansion extends the abbreviation, so for it the list is a hint rather than a limit and the report counts the right answers it found outside it.

`--write` produces, in `data/runs/<run>/`:
- `evaluation_report.md` — the accuracy table per stage, the reliability figures, the errors per step, the candidate coverage of steps 2 and 3, and the abbreviations ranked by how much fixing them would gain.
- `evaluation_mismatches.csv` — every occurrence that is not exactly right, with the gold, the expansion of each stage, the candidates the deciding step was offered (`candidate_miss` says whether the right word was among them) and the source context. This is the file to read when improving a prompt or a glossary entry.
- `evaluation_by_abbreviation.csv` — the same numbers per abbreviation.

Since the gold is model-produced, mismatches that turn out to be errors of the gold go into the `KNOWN_GOLD_ERRORS` table of `evaluate.py` — like the `CORRECTIONS` table of `extract_glossary.py`, each entry carries its reason and a stale one aborts the run, so reviewing `evaluation_mismatches.csv` accumulates instead of being repeated every run.

# Step 6: the TEI output
`to_tei.py` writes `data/rg_expanded.xml`, the final output: one TEI P5 document that holds both readings of the text.

```bash
python to_tei.py            # dry run, prints the report
python to_tei.py --write    # write data/rg_expanded.xml
python to_tei.py --run gemma-4-31b-it --write     # which run to publish
```

Every stage of the workflow produces a text in which the abbreviations have been replaced, which loses the reading of the RG: once `eccl.` has become `ecclesiae` there is no way back. The TEI document keeps both, so either can be read automatically:

```xml
<choice><abbr>eccl.</abbr><expan resp="#step1 #step4">ecclesiae</expan></choice>
```

- the text of the RG — drop the `<expan>` of every `<choice>`
- the expanded text — drop the `<abbr>` of every `<choice>`

An `<abbr>` that stands outside a `<choice>` is an abbreviation the workflow did not resolve; it belongs to both readings, which is why the rule names `<choice>` rather than the elements alone. `to_tei.readings()` implements both and is what the round-trip check uses. `@resp` names the step that decided the expansion, so the expansions made by rule can be told from the ones a model chose without re-running anything. The steps are declared in the `teiHeader`, each with the model that ran it and what was asked of its thinking, read from the manifest of the run being published — a chain may mix models, and a step it borrowed with `--from` says which run it came from:

```xml
<respStmt xml:id="step3"><resp>choice among candidates mined from the RG (taken from the run gemma-4-31b-it)</resp><name>gemma-4-31b-it</name></respStmt>
<respStmt xml:id="step4"><resp>normalisation of the inflection, with thinking off</resp><name>qwen3.8-27b</name></respStmt>
```

Only the steps a run actually reached are declared, which is exactly the set of `@resp` values the markup can use. The structure follows the existing keys: `<div type="volume">` and `<div type="vita">` from volume/nr_RG, one `<head>` or `<p>` per regest with the `xml:id` taken from `id_RG_all`.

The pairing of abbreviation and expansion reuses the alignment of `evaluate.py`. Three things it does not settle have to be decided here, because the markup has to reproduce the source character for character rather than token for token: material *between* two words that only one reading has (`aep.` → `archiepiscopus,` adds a comma) is folded into the neighbouring `<choice>`; a word ending in a period is not necessarily an abbreviation (`fecerunt.` at the end of a sentence, `236v.` as a folio mark), so a token only becomes an `<abbr>` if the glossary lists it; and several abbreviations sharing one expansion (`s.p.d.` → `sineperdatum`) become a single `<choice>`.

Every regest is round-tripped before it is written — the two readings are parsed back out of the markup and compared with the inputs — and a regest that does not reproduce its source exactly is refused and reported in `data/review/tei_report.md` instead of being written wrong. Currently all 528 regests of the 156 vitae round-trip, with 5168 expansions and 17 abbreviations left standing.

# Progress so far
- looked at Lotta's file/script, realised that there still is a significant amount of ambiguity and it's not easily usable for my workflow - also, only ca. 50 percent of the entries were covered, the rest was ignored due to complexity
- explored the Abkürzungsverzeichnis to better understand the complexity
- created a plan for using the information in the glossary
    - expand all abbreviations where a simple rule suffices
    - let an LLM choose the most likely candidate for abbreviations where there are multiple candidates
    - then let an LLM normalise the text
- for this first the information in the glossary needs to be extracted, because it's definitely not yet in a form that can be used programatically
    - I decided to use a script for this, because this ensures reproducibility and makes all decisions I took explicit
    - in case I made a mistake somewhere (misunderstanding something about the glossary), it would also be easier to fix it, by fixing the script and re-running it
- got started on extracting the info (letting ChatGPT-5.4 create a first revision of a script for extracting the information for me)
    - since there is a lot of complexity behind the data and knowledge of Latin helps, using a model that is simply trained to programm, wouldn't have been as helpful, so I decided to use a commercial model for this task, which doesn't need to be reproducible (since the script itself ensures reproducibility)
- made some manual revisions on data in the glossary (there are a lot of inconsistencies and correcting some makes the extraction simpler)
- rewrote the extraction from scratch (`extract_glossary.py`), because in the end I had done more by hand than I wanted and wasn't sure about the quality of the result
    - the hand-edited copy of the glossary and the two hand-made derivatives are gone; the raw export `data/RGAbkVerz.csv` is now the only input, and the ~30 edits that had accumulated in the copy became documented entries in the correction table (each with its reason, and stale ones abort the run)
    - the chain of intermediate CSVs is gone as well: one script does all of it in memory, which also made it possible to state the rules explicitly (when is an abbreviation "complex"? when is a slash an alternative expansion?) instead of having them spread over notebook cells
    - since I'm not great at Latin, the script now also checks its own output against the RG and lists what looks suspicious (see above) rather than leaving me to trust it

# Tests
`tests/` holds one file per module, named after it. They need no data and no network:

```bash
pytest                     # all of them
pytest tests/test_evaluate.py
```

The modules under test live at the top level, so `pyproject.toml` puts the project root on the path (`[tool.pytest.ini_options]`).

# Format of the Wortstamm/Deklination columns
The columns are cleaned by `clean_morphology.py`, which runs as the morphology stage of `extract_glossary.py` (rows it cannot clean keep their values and are written to `data/review/morphology_review.csv`). `paradigm.py` generates the full set of inflected forms per candidate from these columns (`entry_forms(Auflösung, Wortstamm, Deklination)`), e.g. for validating inflected expansions. Step 4 (`normalize.py`, run by `run_step.py 4`) builds on this: every glossary base form that the expansion steps inserted (identified by aligning the expanded text with the original — words that were never abbreviated are excluded; an original word indistinguishable from an adjacent identical insertion counts as inserted) is offered its full paradigm as a multiple-choice list, so the model can fix the inflection but can never change the word.

**Wortstamm** — one part per word of the Auflösung, separated by `; `:
- declinable noun/adjective: `stem -ending` (genitive singular; genitive plural for plural-only words, which are marked `(Pl.)` in Deklination). Stem variants: `stem1/stem2 -ending`; alternative endings: `stem -e/-i`. `ae` is written `e` (the RG uses both spellings, treat them as interchangeable).
- verb: `present, perfect, supine` stems (`-` for a missing stem, variants with `/`)
- fixed word (not inflected, e.g. `et` or an attribute already in the genitive): the word itself, verbatim
- `?` = unknown; a trailing ` ?` marks a part as unverified

**Deklination** — one part per Wortstamm part, separated by `; `:
- nouns: `a`, `o`, `u`, `e`, `i`, `kons.`, `gem.` with optional `(m.)`, `(f.)`, `(n.)`, `(Pl.)` and `/`-alternatives when uncertain
- adjectives/participles: class plus `(Adj.)`, e.g. `o/a (Adj.)`, `i (Adj.)`
- verbs: `a-Konj.`, `e-Konj.`, `i-Konj.`, `kons.-Konj.`, `gem.-Konj.`, `halbkons.-Konj.`, optional `(Dep.)`
- other: `Gerundium`, `Gerundivum`, `Adverb`; `-` = fixed word; `?` = unknown; trailing ` ?` = unverified