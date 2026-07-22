# Workflow

0. Extract the information from the glossary into a structured format (csv), storing information systematically - extract_glossary.py (includes cleaning the morphology columns via clean_morphology.py)
1. Expand abbreviations in the text using the glossary information, where a simple rule suffices - expansion_simple.ipynb
2. For abbreviations where there are multiple candidates, let an LLM choose the most likely - expanding_candidates.ipynb
3. For abbreviations where there are no candidates in the glossary, mine candidates from the RG and suggest these, but let an LLM choose freely - expanding_rest.ipynb
4. Let an LLM normalise the text (e.g. fix inflection, spelling, punctuation, etc.) - normalizing.ipynb

# Step 0: extracting the glossary
`extract_glossary.py` builds `data/simple.csv` and `data/complex.csv` from `data/RGAbkVerz.csv` (the raw export of the Abkürzungsverzeichnis, the source of truth — it is never hand-edited).

```bash
python extract_glossary.py --write
```

Without `--write` it is a dry run that prints the report; `--diff-old` additionally compares the result with the CSVs currently on disk (`data/review/diff_*.csv`), so a re-extraction can be reviewed before it is written.

Every manual decision is an explicit, documented entry in the `CORRECTIONS`/`ADDITIONS` tables of the script rather than an edit in the data — each carries the reason for it, and a correction that no longer matches any row aborts the run, so the tables cannot silently go stale if the export is updated. The remaining stages are documented in the module docstring; in short: continuation rows inherit their abbreviation, the Auflösung is normalised (alternative expansions become separate rows, notation like `op(p)idum` or `subcustos/succustos` is resolved against the abbreviation), the `RG1`–`RG9` columns are reduced to the row's own abbreviation (variants they name become their own rows), abbreviations that never occur in the RG are dropped, and what is left is split into `simple.csv` (step 1 can expand it by rule) and `complex.csv` (needs the LLM in step 2). Finally `clean_morphology.py` cleans the Wortstamm/Deklination columns (see below).

Every run writes `data/review/`:
- `extraction_report.md` — the log of the run: all counts, every applied correction with its reason, and every flagged row. This is the documentation of the extraction.
- `morphology_review.csv` — rows whose Wortstamm/Deklination could not be cleaned automatically (they keep their original values).
- `morphology_unattested.csv` — entries whose generated paradigm has no form at all in the RG (a hint at a wrong stem or declension class).
- `aufloesung_unattested.csv` — Auflösung words that never occur written out in the RG.
- `rg_volume_mismatch.csv` — rows claiming a volume in which the abbreviation is not actually found.

The last three are quality checks against the corpus, not errors: they are the list of entries worth a manual look.

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