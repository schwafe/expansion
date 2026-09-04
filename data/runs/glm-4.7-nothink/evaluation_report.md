# Evaluation of `glm-4.7-nothink` against the gold labels

Gold: `data/to_compare_with/fable_expanded.csv` -- 156 of 156 vitae scored (the rest are missing from a pipeline stage).

## What produced this

| step | model | thinking | run | written |
| --- | --- | --- | --- | --- |
| step 1 | rule (`expand_simple.py`) | | | |
| step 2 | `glm-4.7` | off | `glm-4.7-nothink` | 2026-09-04T10:15:37+00:00 |

## Accuracy per stage

Word accuracy asks whether the right word was chosen (steps 1-3), form accuracy whether the text is right as it stands (step 4).

| stage | scoreable | expanded | word accuracy | form accuracy | exact | orthographic | wrong form | wrong form? | wrong word | not expanded |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| step 1 (rule) | 4967 |  59.7% |  58.8% |  32.6% | 1599 | 18 | 1251 | 54 | 45 | 2000 |
| step 2 (candidates) | 4957 |  92.1% |  86.9% |  43.8% | 2138 | 33 | 1991 | 147 | 258 | 390 |

## Reliability

- 5585 abbreviation occurrences in the source of the scored vitae.
- 618 (11.1%) have no gold label: the gold left the abbreviation standing (`etc.`, month names, place initials) or dropped the passage. They are excluded from every rate -- the pipeline may well have expanded them correctly.
- 10 (0.2%) could not be aligned and are excluded as well. A rising number here means the metric, not the pipeline, is degrading.
- 147 `wrong form?` verdicts rest on the stem-and-ending check that stands in for the paradigm where the glossary knows no morphology (step 3 mines those words from the corpus). They count as the right word, so word accuracy carries that much uncertainty. Step 4 cannot change a word, only its form -- a small dip in word accuracy there is this check reacting to the new ending, not the pipeline losing a word.

## Errors by step

Which step produced the expansion that is finally in the text.

| step | expansions | word accuracy | form accuracy |
| --- | ---: | ---: | ---: |
| step 1 (rule) | 2959 |  98.5% |  54.5% |
| step 2 (candidates) | 1609 |  86.6% |  34.7% |

## Candidate coverage

Steps 2 and 3 do not invent an expansion, they choose one from a list, so an error is only the model's if the list held the right word. `ceiling` is the share of the expansions whose list did; `choice accuracy` scores the step over exactly those, i.e. over the choices it could have made.

| step | expansions | word accuracy | ceiling | choice accuracy | errors | candidate misses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| step 2 (candidates) | 1596 |  86.5% |  96.2% |  89.9% | 215 | 60 (28%) |

- step 2 (candidates): the candidate misses are mostly `supplic.` (48), `exten.` (4), `ap.` (3), `instit.` (2), `abbrev.` (1).
- step 2 (candidates): 13 expansions have no recorded list (a multi-word abbreviation is offered under its whole key, not under its parts) and are left out of this table.
- A candidate counts as covering the gold under the same yardstick as the rest of the report, so a candidate the lemma check cannot connect to the gold form -- verbs above all, which the glossary gives no paradigm -- is counted as a miss although it is in truth the right word. The candidate miss column is therefore an upper bound.

## Worst abbreviations

Sorted by how many occurrences fixing them would gain.

| abbreviation | occurrences | word accuracy | form accuracy | most frequent wrong expansion | gold |
| --- | ---: | ---: | ---: | --- | --- |
| `eccl.` | 401 |  83.5% |  46.4% | ecclesia | ecclesia, ecclesiam, ecclesiarum, ecclesie, ecclesiis |
| `d.` | 157 |  72.0% |   3.2% | dictus | d., data, dicta, dictam, dictarum |
| `s.` | 252 |  94.0% |  51.2% | sanctus | s., sacri, sancte, sancti, sine |
| `o.` | 132 |  97.7% |  25.8% | ordo | obitum, obstante, obstantibus, ordinis |
| `op.` | 110 | 100.0% |  16.4% | opidum | opidi, opido, opidorum, opidum |
| `an.` | 84 | 100.0% |   0.0% | annus | anni, annis, annorum, annos, annum |
| `b.` | 83 |  94.0% |   0.0% | beatus | b., beate |
| `par.` | 150 |  98.7% |  54.0% | parochialis | parente, parochialem, parochiales, parochiali, parochialibus |
| `mai.` | 58 |  81.0% |   0.0% | maius | mai., maii, maiorem, maiores, maiori |
| `mon.` | 86 | 100.0% |  33.7% | monasterium | monasteria, monasterii, monasteriis, monasterio, monasteriorum |
| `can.` | 72 |  93.1% |  25.0% | canonicatus | canonicas, canonicatibus, canonicatu, canonicatum, canonicatus |
| `supplic.` | 50 |   4.0% |   0.0% | supplicatio | supplic., supplicante, supplicantibus, supplicat, supplicationis |
| `conc.` | 46 |  30.4% |   4.3% | concessio | concedant, conceditur, concessa, concessarum, concesserunt |
| `m.` | 83 |  91.6% |  49.4% | marca | mandati, mandato, mandatum, marcarum, minorum |
| `preb.` | 60 | 100.0% |  33.3% | prebenda | prebenda, prebendam, prebendarum, prebendas, prebende |
| `conf.` | 42 |  88.1% |   9.5% | confirmatio | conf., confessorem, confirmata, confirmati, confirmatio |
| `dec.` | 53 |  94.3% |  37.7% | december | dec., decani, decano, decanus, decembris |
| `ss.` | 32 | 100.0% |   0.0% | sancti | sanctarum, sanctorum |
| `iul.` | 29 | 100.0% |   0.0% | iulius | iul., iulii |
| `vac.` | 29 |  89.7% |  10.3% | vacante | vacante, vacantes, vacantibus, vacantis, vacantium |
| `Cist.` | 24 |  87.5% |   0.0% | Cisterciensium | Cisterciensis |
| `Camin.` | 48 | 100.0% |  50.0% | Caminensis | Caminensem, Caminensi, Caminensibus, Caminensis, Caminensium |
| `oct.` | 23 | 100.0% |   0.0% | october | oct., octobris |
| `febr.` | 20 | 100.0% |   0.0% | februarius | febr., februarii |
| `iun.` | 20 | 100.0% |   0.0% | iunius | iun., iunii, iuniorem, iunioris |

## Sample mismatches

The full list is in `evaluation_mismatches.csv`.

- 2/370 `conc.`: gold **concessio**, system **concedere** (step 2 (candidates)) -- _et cives civ. Magdeburg. conc. indulg. iubilei visitantibus eccl._
- 2/370 `mai.`: gold **maiorem**, system **maius** (step 2 (candidates)) -- _indulg. iubilei visitantibus eccl. mai. domum fr. herem. s._
- 2/370 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _visitantibus eccl. mai. domum fr. herem. s. Aug. Magdeburg._
- 2/370 `herem.`: gold **heremitarum**, system **herem.** (None) -- _eccl. mai. domum fr. herem. s. Aug. Magdeburg. eccl._
- 2/370 `Aug.`: gold **Augustini**, system **Aug.** (None) -- _domum fr. herem. s. Aug. Magdeburg. eccl. s. Johannis_
- 2/370 `Terdon.`: gold **Terdonensis**, system **Terdon.** (None) -- _Percipiano o. s. Ben. Terdon. dioc. nuntio et Bartholomeo_
- 2/370 `Lucan.`: gold **Lucano**, system **Lucan.** (None) -- _Bartholomeo de Turchiis civi Lucan. assignatarum medietas in fabricam_
- 2/370 `d.`: gold **dicte**, system **dominus** (step 2 (candidates)) -- _altera medietas in fabricam d. eccl. Magdeburg. 26 apr._
- 2/370 `Terdon.`: gold **Terdonensis**, system **Terdon.** (None) -- _Percipiano o. s. Ben. Terdon. dioc. conc. lic. quod_
- 2/370 `conc.`: gold **concessio**, system **concedere** (step 2 (candidates)) -- _s. Ben. Terdon. dioc. conc. lic. quod alter ipsorum_
- 2/370 `iubil.`: gold **iubilei**, system **iubil.** (None) -- _absente litteras de indulg. iubil. in prov. Magdeburg. possit_
- 2/370 `mai.`: gold **maiori**, system **maius** (step 2 (candidates)) -- _quattuor cistas in eccl. mai. dom. fr. herem. s._
- 2/370 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _in eccl. mai. dom. fr. herem. s. Aug. eccl._
- 2/370 `herem.`: gold **heremitarum**, system **herem.** (None) -- _eccl. mai. dom. fr. herem. s. Aug. eccl. s._
- 2/370 `Aug.`: gold **Augustini**, system **Aug.** (None) -- _dom. fr. herem. s. Aug. eccl. s. Johannis in_
- 2/370 `cellerar.`: gold **cellerarius**, system **cellerar.** (None) -- _scolast. Walterus de Kokeritz cellerar. Meynhardus de Weringerade inter_
- 2/370 `o.`: gold **obitum**, system **obstantibus** (step 2 (candidates)) -- _divisionem fecerunt. deinde post o. Benedicti abb. mon. s._
- 2/370 `Terdon.`: gold **Terdonensis**, system **Terdon.** (None) -- _Percipiano o. s. Ben. Terdon. dioc. ad ipsius hosp._
- 2/370 `cellerar.`: gold **cellerario**, system **cellerar.** (None) -- _scolast. Waltero de Kokeritz cellerar. can. Magdeburg. evocandis quia_
- 2/370 `conf.`: gold **confirmatione**, system **conf.** (None) -- _248 conf. instr. de conf. oppignorationis medietatis castri de_
- 2/370 `Magunt.`: gold **Maguntino**, system **Maguntinensis** (step 1 (rule)) -- _quond. Ludovico Magdeburg. tunc Magunt. aep. Balthasari. Thuringiae landgravio_
- 2/370 `Magunt.`: gold **Maguntinos**, system **Maguntinensis** (step 1 (rule)) -- _Ludovicum et Adolfum aep. Magunt. facta a Cristiano ep._
- 2/645 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _Aschersleve eccl. domus fr. min. op. Halberstad. dioc._
- 2/913 `procons.`: gold **proconsules**, system **procons.** (None) -- _Brunswic procons. etc. op. Halberstad. dioc._
- 2/913 `procons.`: gold **proconsules**, system **procons.** (None) -- _mai. 1390 R 103 procons. etc. op. Halberstad. dioc._
- 2/913 `procons.`: gold **proconsules**, system **procons.** (None) -- _1390 L 12 139 procons. etc. op. Halberstad. dioc._
- 2/913 `d.`: gold **dicto**, system **d.** (None) -- _et officiales vicarios in d. opido instituant 8 aug._
- 2/913 `procons.`: gold **proconsules**, system **procons.** (None) -- _1391 L 10 231 procons. etc. op. Halberstad. dioc._
- 2/913 `dec.`: gold **decano**, system **dec.** (None) -- _ut iam antea Rolando dec. eccl. s. Blasii in_
- 2/913 `d.`: gold **dicto**, system **d.** (None) -- _eccl. s. Blasii in d. op. publ. constit. Provide_
- 2/913 `dec.`: gold **decani**, system **dec.** (None) -- _L 79 224 mensa dec. etc. eccl. s. Blasii_
- 2/916 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _eccl. b. Marie dom. fr. min. Misnen. dioc. indulg._
- 2/916 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _eccl. b. Marie dom. fr. min. Misnen. dioc. indulg._
- 2/2229 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _eccl. b. Marie dom. fr. min. Misnen. dioc. indulg._
- 2/2322 `Cist.`: gold **Cisterciensis**, system **Cist.** (None) -- _s. Nicolai prope mon. Cist. o. Nuemburg. dioc. indulg._
- 2/2322 `Hamburg.`: gold **Hamburgensis**, system **Hamburg.** (None) -- _instar eccl. b. Marie Hamburg. Bremen. dioc. 15 sept._
- 2/2411 `visit.`: gold **visitandi**, system **visitatio** (step 2 (candidates)) -- _Wilhelmus marchio Misnen. lic. visit. omnia mon. monial. in_
- 2/2411 `conc.`: gold **concessio**, system **concedere** (step 2 (candidates)) -- _L 30 327 v. conc. ius patr. 4 can._
- 2/2411 `Cist.`: gold **Cisterciensis**, system **Cist.** (None) -- _Antiquecelle et mon. Buech Cist. o. Misnen. dioc. 26_
- ...
