# Workflow

0. Extract the information from the glossary into a structured format (csv), storing information systematically - extract_glossary.py (includes cleaning the morphology columns via clean_morphology.py)
1. Expand abbreviations in the text using the glossary information, where a simple rule suffices - expand_simple.py
2. For abbreviations where there are multiple candidates, let an LLM choose the most likely - run_step.py 2
3. For abbreviations where there are no candidates in the glossary, mine candidates from the RG and suggest these, but let an LLM choose freely - run_step.py 3
4. Let an LLM normalise the text (e.g. fix inflection, spelling, punctuation, etc.) - run_step.py 4
5. Measure the result against the gold labels, so a change to the workflow can be judged by a number - evaluate.py
6. Write the result as a TEI document that holds both the text of the RG and the expansion - to_tei.py

# Step 0: extracting the glossary
`extract_glossary.py` builds `data/simple.csv` and `data/complex.csv` from `data/RGAbkVerz.csv` (the raw export of the Abkürzungsverzeichnis, the source of truth — it is never hand-edited).

```bash
python extract_glossary.py --write
```

Without `--write` it is a dry run that prints the report; `--diff-old` additionally compares the result with the CSVs currently on disk (`data/review/diff_*.csv`), so a re-extraction can be reviewed before it is written.

Every manual decision is an explicit, documented entry in the `CORRECTIONS`/`ADDITIONS` tables of the script rather than an edit in the data — each carries the reason for it, and a correction that no longer matches any row aborts the run, so the tables cannot silently go stale if the export is updated. The remaining stages are documented in the module docstring; in short: continuation rows inherit their abbreviation, the Auflösung is normalised (alternative expansions become separate rows, notation like `op(p)idum` or `subcustos/succustos` is resolved against the abbreviation, and where the abbreviation fits both spellings the more frequent one in the RG wins), the `RG1`–`RG9` columns are reduced to the row's own abbreviation (variants they name become their own rows), abbreviations that never occur in the RG are dropped, and what is left is split into `simple.csv` (step 1 can expand it by rule) and `complex.csv` (needs the LLM in step 2). Finally `clean_morphology.py` cleans the Wortstamm/Deklination columns (see below).

Every run writes `data/review/`:
- `extraction_report.md` — the log of the run: all counts, every applied correction with its reason, and every flagged row. This is the documentation of the extraction.
- `morphology_review.csv` — rows whose Wortstamm/Deklination could not be cleaned automatically (they keep their original values).
- `morphology_unattested.csv` — entries whose generated paradigm has no form at all in the RG (a hint at a wrong stem or declension class).
- `aufloesung_unattested.csv` — Auflösung words that never occur written out in the RG.
- `rg_volume_mismatch.csv` — rows claiming a volume in which the abbreviation is not actually found.

The last three are quality checks against the corpus, not errors: they are the list of entries worth a manual look.

# Step 1: expansion by rule
`expand_simple.py` expands what needs no judgement: an abbreviation for which the volume at hand knows exactly one Auflösung. This is the only step that runs over the whole RG rather than over the test subset.

```bash
python expand_simple.py            # dry run, prints the report
python expand_simple.py --write    # write data/once_expanded.csv
```

Where a volume lists several Auflösungen for the same abbreviation, nothing is substituted — that is what step 2 decides, one occurrence at a time. Two decisions in this step are not forced by the data and are worth stating:

- **Volume columns.** A row whose `RG1`–`RG9` columns are all empty and whose abbreviation appears nowhere else in the glossary is read as applying to every volume. The glossary simply does not record a volume for those entries, and since no other row claims the abbreviation, no reading can be lost by it. A row that is empty *and* has siblings is left alone: there the volume columns are precisely what tells the readings apart.
- **Volume 10.** The glossary has no rules for it, so it is dropped here and never reaches the later steps.

The substitution uses `multiple_choice.occurrence_pattern`, the same pattern step 2 marks its occurrences with, so both steps agree on where an abbreviation begins and ends — in particular on the optional spaces inside a multi-word abbreviation (`e. m.` and `e.m.`). Longer abbreviations are applied first, so `s. p. d.` is resolved as a whole and never as three separate parts. No expansion contains a period and every abbreviation ends in one, so an expansion can never be expanded again.

`--write` produces `data/once_expanded.csv` and `data/review/expansion_report.md` — how many abbreviations the substitution resolved, how many rules each volume could apply, the most frequent abbreviations before and after, and what a clearer glossary entry would gain (the abbreviations still standing although the glossary knows them, ranked by how often they occur).

# Steps 2–4: the model-driven passes
The three passes differ only in what they ask the model and what they let it answer. The loop around them is the same and lives in `run_step.py`: read the output of the previous step, take one vita at a time, mark the occurrences in the text, ask the model, substitute its answer programmatically, record what happened.

```bash
python run_step.py 2                       # the whole subset
python run_step.py 3 --limit 5             # a trial run, writes no output
python run_step.py 4 --resume              # continue an interrupted run
python run_step.py 2 --model qwen3.6-35b-a3b
```

**The model never rewrites the text.** Each occurrence is marked as `[[id|abbreviation]]` and the model returns only a JSON object mapping id to its answer; the substitution happens in code. That replaced an earlier full-text rewrite which corrupted words it should not have touched (`Halberstad.` → `Halhalstad.`), silently expanded abbreviations it had no business expanding, and needed a fragile token diff to validate. Everything the model may change is decided before the call and checked after it, so a bad answer can only leave the text as it was: step 2 accepts only a candidate from the list it offered, step 3 only an expansion that continues the letters of the abbreviation, step 4 only a form from the word's own paradigm.

**Checkpoints.** A run is 150+ model calls at 15 calls a minute, so it has to survive being interrupted. Every vita is appended to `data/checkpoints/step<n>.jsonl` as it is finished (flushed every ten by default, `--checkpoint-every` to change it), and `--resume` processes only what is missing. The CSV and the JSON dump are written only once every vita is done, so an interrupted or `--limit`ed run never overwrites a complete output with a partial one.

**What a run leaves behind.** The CSV for the next step, a dump of every decision (`data/results_candidates.json`, `data/results_rest.json`, `data/results_normalize.json`) that also records the model and the prompt it was produced with — so the evaluation and the TEI header can state where an expansion comes from instead of having to be told — and `data/review/step<n>_report.md` with the acceptance tiers, the errors and the most frequent changes.

**Trying something by hand.** `expanding_candidates.ipynb`, `expanding_rest.ipynb` and `normalizing.ipynb` are probes: they import from `run_step.py` and run a single vita, showing the text, the candidates, the whole prompt, the result and every decision. What is tried there is exactly what the batch does, and `prepare(STEPS[2], model=...)` switches the model for the experiment.

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
python evaluate.py                  # print the summary
python evaluate.py --write          # also write data/review/evaluation_*
python evaluate.py --save-baseline  # store the current numbers as the baseline
python evaluate.py --baseline       # print the change against the baseline
```

The unit of measurement is the single abbreviation, not the text: a text-level diff mixes one expansion error with twenty inflection differences and tells you nothing actionable. The abbreviated source text is the anchor — for each vita it is aligned with the gold and with each stage output at word level, so every abbreviation gets a gold expansion and a system expansion that are compared directly. The alignment works because the expansion steps only ever replace abbreviations, so every word that was not abbreviated reappears unchanged and anchors the alignment (the property `normalize.py` already relies on); inside a changed passage each abbreviation is re-anchored on the expansion that continues it (`eccl.` → `ecclesiam`, or via the glossary where it does not, `aep.` → `archiepiscopus`). What cannot be anchored is reported as `unaligned` and left out of every rate rather than scored — that number is the reliability check on the metric itself.

Two rates are reported per stage, because a single exact-match number would score `thrice_expanded` (deliberately base forms) as broken:
- **word accuracy** — was the right word chosen? This is what steps 1–3 do; it should rise from step 1 to step 3 and stay flat at step 4, which cannot change a word.
- **form accuracy** — is the text right as it stands? This is what step 4 has to move.

Two expansions count as the same form when their spelling variants agree (`ecclesiae`/`ecclesie`, `opidum`/`oppidum`, `parochialis`/`parrochialis`), and as the same word when the glossary paradigms say so (`paradigm.entry_forms`, the same forms step 4 may choose from); for words the glossary has no morphology for (step 3 mines them from the corpus) a shared stem plus a real case ending stands in, reported as `wrong form?` so the uncertainty stays visible. Abbreviations the gold itself leaves standing (`etc.`, month names, place initials) get `no_gold_label` and are excluded — the pipeline may well have expanded them correctly, there is just nothing to compare against.

Every occurrence is also attributed to the step that produced its expansion, by comparing the four stage texts, so a wrong word can be traced to a wrong rule (step 1), a bad candidate choice (step 2) or a bad corpus suggestion (step 3).

Steps 2 and 3 do not invent an expansion, they choose one from a list, so a wrong word is only the model's fault if the list held the right one. The candidate lists are read back from the dumps the two steps wrote (`data/results_candidates.json`, `data/results_rest.json`) — an entry counts only if the text it records is exactly the stage text being scored, so a dump left over from an earlier run cannot be counted against the current one. Each error is then split into a **candidate miss** (no offered candidate would have scored as the right word, whatever the model had picked) and a choice error, which gives the report a **ceiling** — the accuracy the step could have reached — and a **choice accuracy** over exactly the occurrences it could have got right. Step 3 may also expand freely as long as the expansion extends the abbreviation, so for it the list is a hint rather than a limit and the report counts the right answers it found outside it.

`--write` produces `data/review/`:
- `evaluation_report.md` — the accuracy table per stage, the reliability figures, the errors per step, the candidate coverage of steps 2 and 3, and the abbreviations ranked by how much fixing them would gain.
- `evaluation_mismatches.csv` — every occurrence that is not exactly right, with the gold, the expansion of each stage, the candidates the deciding step was offered (`candidate_miss` says whether the right word was among them) and the source context. This is the file to read when improving a prompt or a glossary entry.
- `evaluation_by_abbreviation.csv` — the same numbers per abbreviation.

Since the gold is model-produced, mismatches that turn out to be errors of the gold go into the `KNOWN_GOLD_ERRORS` table of `evaluate.py` — like the `CORRECTIONS` table of `extract_glossary.py`, each entry carries its reason and a stale one aborts the run, so reviewing `evaluation_mismatches.csv` accumulates instead of being repeated every run.

# Step 6: the TEI output
`to_tei.py` writes `data/rg_expanded.xml`, the final output: one TEI P5 document that holds both readings of the text.

```bash
python to_tei.py            # dry run, prints the report
python to_tei.py --write    # write data/rg_expanded.xml
```

Every stage of the workflow produces a text in which the abbreviations have been replaced, which loses the reading of the RG: once `eccl.` has become `ecclesiae` there is no way back. The TEI document keeps both, so either can be read automatically:

```xml
<choice><abbr>eccl.</abbr><expan resp="#step1 #step4">ecclesiae</expan></choice>
```

- the text of the RG — drop the `<expan>` of every `<choice>`
- the expanded text — drop the `<abbr>` of every `<choice>`

An `<abbr>` that stands outside a `<choice>` is an abbreviation the workflow did not resolve; it belongs to both readings, which is why the rule names `<choice>` rather than the elements alone. `to_tei.readings()` implements both and is what the round-trip check uses. `@resp` names the step that decided the expansion (declared in the teiHeader with the model that ran it), so the expansions made by rule can be told from the ones a model chose without re-running anything. The structure follows the existing keys: `<div type="volume">` and `<div type="vita">` from volume/nr_RG, one `<head>` or `<p>` per regest with the `xml:id` taken from `id_RG_all`.

The pairing of abbreviation and expansion reuses the alignment of `evaluate.py`. Three things it does not settle have to be decided here, because the markup has to reproduce the source character for character rather than token for token: material *between* two words that only one reading has (`aep.` → `archiepiscopus,` adds a comma) is folded into the neighbouring `<choice>`; a word ending in a period is not necessarily an abbreviation (`fecerunt.` at the end of a sentence, `236v.` as a folio mark), so a token only becomes an `<abbr>` if the glossary lists it; and several abbreviations sharing one expansion (`s.p.d.` → `sineperdatum`) become a single `<choice>`.

Every regest is round-tripped before it is written — the two readings are parsed back out of the markup and compared with the inputs — and a regest that does not reproduce its source exactly is refused and reported in `data/review/tei_report.md` instead of being written wrong. Currently all 528 regests of the 156 vitae round-trip, with 5168 expansions and 17 abbreviations left standing.

# Dates and references in the text
`extract_dates_refs.py` marks the two parts of a text that are not Latin prose: the date of the entry and the reference to the register it was taken from.

```bash
python extract_dates_refs.py            # print the report
python extract_dates_refs.py --write    # also write data/dates_refs.csv and data/review/dates_refs_*
```

A regest normally ends with both of them — `... n. o. par. eccl. de Kalkar Colon. dioc., 21 mart. 1392 L 23 21v.` — but not always: a second register may be cited after an intervening remark, and the date of an earlier grant can stand in the middle of the sentence. So both are looked for everywhere in the text and reported as spans (`find_spans(text)` gives them in order, with their offsets); `main_date`/`main_reference` pick the pair that belongs to the entry itself.

The rules are deliberately small:
- a **date** is a day/month/year group written with one of the RG's month abbreviations (`21 mart. 1392`, `6. sept. 80`, `mai. 1450`, `4. iul. [1452]`), or one of the formulas standing in for a missing one (`s. d.`, `sine dat.`, `sub priori dato`). The month is what is looked for, day and year are the numbers to its left and right. The one ambiguity this creates is settled by a rule of its own: a number between two months (`... eccl. mai. 22 iun. 1396`) is the day of the second, not the year of the first, unless it is written out as a full year.
- a **reference** is a citation `SIGLUM VOLUME FOLIO` (`L 23 21v.`), the siglum taken from a closed list, the volume allowed a few tokens for the funds cited by name (`Arm. XXXIV 4 91.`, `Florenz, Magl. Classe XXXI, 63 14v.`) and the folio allowed lists and ranges (`S 174 89,92.`, `V 420 122r-123v.`). Citations following each other are one reference. The closed siglum list is what keeps an ordinary capitalised word followed by a number from being read as a citation; dates are matched first and their stretches are not searched again, so `s. A. 30 mai. 1421` cannot lose its day to a citation `A. 30`.
- of two dates the entry's own is the last one that does not stand behind an `exped.` (the date of despatch, which the RG adds to the date of the grant).

The dates have a gold label in the source table — the `date_sublemma` column — and the extraction is measured against it; the references have none and are checked structurally instead (a reference ends its regest, so whatever follows one is a piece of reference that was missed). Currently the date of 96.6% of the 155,675 dated regests is found exactly, 99.0% of all regests get a reference and in 98.5% it reaches the end of the text. `data/review/dates_refs_report.md` holds the numbers, `data/review/dates_refs_mismatches.csv` every regest whose date differs from the gold, labelled by *how* it differs.

`data/dates_refs.csv` is one row per text (join key `id_RG_all`, `part` tells a header from a regest) with the date and the reference, their offsets, how many of each the text has, and `rest` — the text with both cut out. It is not in the repository for the same reason the source table is not: it is 74 MB and rebuilt in twenty seconds.

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

The project root is on the path via the `conftest.py` next to this file, which exists for that alone.

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