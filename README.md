# Workflow

0. Extract the information from the glossary into a structured format (csv), storing information systematically - extract_glossary.py (includes cleaning the morphology columns via clean_morphology.py)
1. Expand abbreviations in the text using the glossary information, where a simple rule suffices - expansion_simple.ipynb
2. For abbreviations where there are multiple candidates, let an LLM choose the most likely - expanding_candidates.ipynb
3. For abbreviations where there are no candidates in the glossary, mine candidates from the RG and suggest these, but let an LLM choose freely - expanding_rest.ipynb
4. Let an LLM normalise the text (e.g. fix inflection, spelling, punctuation, etc.) - normalizing.ipynb
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

# Format of the Wortstamm/Deklination columns
The columns are cleaned by `clean_morphology.py`, which runs as the morphology stage of `extract_glossary.py` (rows it cannot clean keep their values and are written to `data/review/morphology_review.csv`). `paradigm.py` generates the full set of inflected forms per candidate from these columns (`entry_forms(Auflösung, Wortstamm, Deklination)`), e.g. for validating inflected expansions. Step 4 (`normalize.py` / `normalizing.ipynb`) builds on this: every glossary base form that the expansion steps inserted (identified by aligning the expanded text with the original — words that were never abbreviated are excluded; an original word indistinguishable from an adjacent identical insertion counts as inserted) is offered its full paradigm as a multiple-choice list, so the model can fix the inflection but can never change the word.

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