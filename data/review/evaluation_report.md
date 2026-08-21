# Evaluation against the gold labels

Gold: `data/to_compare_with/fable_expanded.csv` -- 156 of 156 vitae scored (the rest are missing from a pipeline stage).

## Accuracy per stage

Word accuracy asks whether the right word was chosen (steps 1-3), form accuracy whether the text is right as it stands (step 4).

| stage | scoreable | expanded | word accuracy | form accuracy | exact | orthographic | wrong form | wrong form? | wrong word | not expanded |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| step 1 (rule) | 4967 |  60.5% |  59.0% |  32.7% | 1606 | 18 | 1253 | 54 | 73 | 1963 |
| step 2 (candidates) | 4967 |  93.6% |  87.9% |  43.4% | 2124 | 33 | 2060 | 150 | 283 | 317 |
| step 3 (mined) | 4967 |  99.2% |  92.9% |  46.4% | 2264 | 39 | 2108 | 202 | 316 | 38 |
| step 4 (normalized) | 4967 |  99.2% |  92.9% |  64.8% | 2915 | 305 | 1191 | 201 | 317 | 38 |

## Reliability

- 5585 abbreviation occurrences in the source of the scored vitae.
- 618 (11.1%) have no gold label: the gold left the abbreviation standing (`etc.`, month names, place initials) or dropped the passage. They are excluded from every rate -- the pipeline may well have expanded them correctly.
- 0 (0.0%) could not be aligned and are excluded as well. A rising number here means the metric, not the pipeline, is degrading.
- 201 `wrong form?` verdicts rest on the stem-and-ending check that stands in for the paradigm where the glossary knows no morphology (step 3 mines those words from the corpus). They count as the right word, so word accuracy carries that much uncertainty. Step 4 cannot change a word, only its form -- a small dip in word accuracy there is this check reacting to the new ending, not the pipeline losing a word.

## Errors by step

Which step produced the expansion that is finally in the text.

| step | expansions | word accuracy | form accuracy |
| --- | ---: | ---: | ---: |
| step 1 (rule) | 2107 |  97.4% |  71.0% |
| step 2 (candidates) | 930 |  84.6% |  55.6% |
| step 3 (mined) | 276 |  88.0% |  52.5% |
| step 4 (normalized) | 1616 |  94.6% |  65.8% |

## Candidate coverage

Steps 2 and 3 do not invent an expansion, they choose one from a list, so an error is only the model's if the list held the right word. `ceiling` is the share of the expansions whose list did; `choice accuracy` scores the step over exactly those, i.e. over the choices it could have made.

| step | expansions | word accuracy | ceiling | choice accuracy | errors | candidate misses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| step 2 (candidates) | 918 |  84.4% |  94.1% |  89.7% | 143 | 54 (38%) |
| step 3 (mined) | 276 |  88.0% |  61.6% |  92.9% | 33 | 21 (64%) |

- step 2 (candidates): the candidate misses are mostly `supplic.` (45), `exten.` (4), `ap.` (2), `abbrev.` (1), `s.` (1).
- step 2 (candidates): 12 expansions have no recorded list (a multi-word abbreviation is offered under its whole key, not under its parts) and are left out of this table.
- step 3 (mined): the candidate misses are mostly `Terdon.` (3), `Erford.` (3), `Par.` (3), `Liptzen.` (2), `Conc.` (2).
- step 3 (mined): 85 of its right answers were not in its list at all -- the step may expand freely as long as the expansion extends the abbreviation, so for it the list is a hint, not a limit.
- A candidate counts as covering the gold under the same yardstick as the rest of the report, so a candidate the lemma check cannot connect to the gold form -- verbs above all, which the glossary gives no paradigm -- is counted as a miss although it is in truth the right word. The candidate miss column is therefore an upper bound.

## Worst abbreviations

Sorted by how many occurrences fixing them would gain.

| abbreviation | occurrences | word accuracy | form accuracy | most frequent wrong expansion | gold |
| --- | ---: | ---: | ---: | --- | --- |
| `eccl.` | 402 | 100.0% |  68.9% | ecclesie | ecclesia, ecclesiam, ecclesiarum, ecclesie, ecclesiis |
| `d.` | 158 |  89.9% |  55.1% | dictae | d., data, dicta, dictam, dictarum |
| `an.` | 84 | 100.0% |  22.6% | annis | anni, annis, annorum, annos, annum |
| `par.` | 151 |  98.7% |  63.6% | parochialis | parente, parochialem, parochiales, parochiali, parochialibus |
| `can.` | 72 |  94.4% |  25.0% | canonicatus | canonicas, canonicatibus, canonicatu, canonicatum, canonicatus |
| `supplic.` | 50 |   4.0% |   4.0% | supplicatio | supplic., supplicante, supplicantibus, supplicat, supplicationis |
| `mai.` | 58 | 100.0% |  22.4% | maius | mai., maii, maiorem, maiores, maiori |
| `dec.` | 53 |  62.3% |  28.3% | december | dec., decani, decano, decanus, decembris |
| `conc.` | 46 |  39.1% |  19.6% | concessio | concedant, conceditur, concessa, concessarum, concesserunt |
| `preb.` | 60 | 100.0% |  40.0% | prebenda | prebenda, prebendam, prebendarum, prebendas, prebende |
| `o.` | 132 | 100.0% |  73.5% | obstante | obitum, obstante, obstantibus, ordinis |
| `ss.` | 32 | 100.0% |   6.2% | sancti | sanctarum, sanctorum |
| `m.` | 83 |  90.4% |  66.3% | marcae | mandati, mandato, mandatum, marcarum, minorum |
| `op.` | 111 | 100.0% |  76.6% | opidi | opidi, opido, opidorum, opidum |
| `vac.` | 29 |  89.7% |  10.3% | vacante | vacante, vacantes, vacantibus, vacantis, vacantium |
| `Camin.` | 48 | 100.0% |  50.0% | Caminensis | Caminensem, Caminensi, Caminensibus, Caminensis, Caminensium |
| `mon.` | 86 | 100.0% |  73.3% | monasterio | monasteria, monasterii, monasteriis, monasterio, monasteriorum |
| `Cist.` | 24 |  95.8% |   8.3% | Cisterciensium | Cisterciensis |
| `mart.` | 19 |  94.7% |   0.0% | martius | mart., martii, martiris, martirum |
| `Magdeburg.` | 43 | 100.0% |  58.1% | Magdeburgensis | Magdeburgensem, Magdeburgenses, Magdeburgensi, Magdeburgensibus, Magdeburgensis |
| `Misnen.` | 92 | 100.0% |  81.5% | Misnensis | Misnen., Misnensem, Misnenses, Misnensi, Misnensibus |
| `fr.` | 17 |  17.6% |   5.9% | frater | fratrem, fratres, fratrum |
| `s.` | 252 |  96.8% |  94.0% | sancti | s., sacri, sancte, sancti, sine |
| `ian.` | 19 | 100.0% |  21.1% | ianuarius | ian., ianuarii |
| `vicar.` | 23 | 100.0% |  34.8% | vicaria | vicaria, vicariam, vicarie, vicariis |

## Sample mismatches

The full list is in `evaluation_mismatches.csv`.

- 2/370 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _visitantibus eccl. mai. domum fr. herem. s. Aug. Magdeburg._
- 2/370 `Terdon.`: gold **Terdonensis**, system **Terdonis** (step 3 (mined)) -- _Percipiano o. s. Ben. Terdon. dioc. nuntio et Bartholomeo_
- 2/370 `Lucan.`: gold **Lucano**, system **Lucanensis** (step 3 (mined)) -- _Bartholomeo de Turchiis civi Lucan. assignatarum medietas in fabricam_
- 2/370 `Terdon.`: gold **Terdonensis**, system **Terdonis** (step 3 (mined)) -- _Percipiano o. s. Ben. Terdon. dioc. conc. lic. quod_
- 2/370 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _in eccl. mai. dom. fr. herem. s. Aug. eccl._
- 2/370 `Terdon.`: gold **Terdonensis**, system **Terdonis** (step 3 (mined)) -- _Percipiano o. s. Ben. Terdon. dioc. ad ipsius hosp._
- 2/370 `assign.`: gold **assignandi**, system **assignationis** (step 4 (normalized)) -- _V 315 164 m. assign. pecunias a capitulo exactas_
- 2/370 `Magunt.`: gold **Maguntino**, system **Maguntinensis** (step 1 (rule)) -- _quond. Ludovico Magdeburg. tunc Magunt. aep. Balthasari. Thuringiae landgravio_
- 2/370 `Magunt.`: gold **Maguntinos**, system **Maguntinensis** (step 1 (rule)) -- _Ludovicum et Adolfum aep. Magunt. facta a Cristiano ep._
- 2/645 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _Aschersleve eccl. domus fr. min. op. Halberstad. dioc._
- 2/916 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _eccl. b. Marie dom. fr. min. Misnen. dioc. indulg._
- 2/916 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _eccl. b. Marie dom. fr. min. Misnen. dioc. indulg._
- 2/2229 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _eccl. b. Marie dom. fr. min. Misnen. dioc. indulg._
- 2/2411 `Cist.`: gold **Cisterciensis**, system **Cisterdorf** (step 3 (mined)) -- _Antiquecelle et mon. Buech Cist. o. Misnen. dioc. 26_
- 2/2411 `decan.`: gold **decanatu**, system **decano** (step 3 (mined)) -- _lic. fundandi collegium c. decan. et can. apud capellam_
- 2/2411 `m.`: gold **mandatum**, system **manu** (step 4 (normalized)) -- _1400 L 90 100 m. conf. perm. fact. inter_
- 2/2411 `el.`: gold **eligendi**, system **electionis** (step 4 (normalized)) -- _L 90 101 lic. el. confess. 31 mart. 1401_
- 2/2411 `confess.`: gold **confessorem**, system **confessionis** (step 4 (normalized)) -- _90 101 lic. el. confess. 31 mart. 1401 L_
- 2/5209 `ap.`: gold **apostolorum**, system **apostolicus** (step 2 (candidates)) -- _regum necnon bb. XII ap. ac X mil. martirum_
- 2/5209 `fr.`: gold **fratrum**, system **frater** (step 1 (rule)) -- _L 90 273 confraternitas fr. kalend. conf. 1 aug._
- 2/6133 `Sagan.`: gold **Saganensi**, system **Sagani** (step 3 (mined)) -- _marchioni Moravie et duci Sagan. discussionem sup. concordia inter_
- 2/6133 `Luben.`: gold **Lubense**, system **Lubencii** (step 3 (mined)) -- _d. mon. et mon. Luben. d. o. Wratislav. dioc._
- 2/6177 `fund.`: gold **fundata**, system **fundatio** (step 2 (candidates)) -- _dioc. capella s. Georgii fund. a Giselberto Dobberkow decr._
- 2/6177 `fund.`: gold **fundata**, system **fundatio** (step 2 (candidates)) -- _dioc. capella s. Georgii fund. a Giselberto Dobberkow decr._
- 2/6177 `m.`: gold **mandatum**, system **memoria** (step 2 (candidates)) -- _in eccl. s. Nicolai m. quod Johannes Schymming rect._
- 2/6177 `fund.`: gold **fundatum**, system **fundatio** (step 2 (candidates)) -- _bonis d. mon. est fund. 22 mart. 1403 L_
- 3/1990 `constit.`: gold **constitui**, system **constitutionem** (step 4 (normalized)) -- _in colleg. eccl. fecerat constit. cum par. eccl. s._
- 3/1990 `incorp.`: gold **incorporata**, system **incorporatio** (step 2 (candidates)) -- _dicti castri in ipsa incorp. ac par. eccl. in_
- 3/1990 `instit.`: gold **instituendi**, system **institutione** (step 4 (normalized)) -- _marchione Brandenburg. ac iuris instit. prep. et can. ac_
- 3/1990 `dec.`: gold **decano**, system **decanatus** (step 2 (candidates)) -- _can. ac Visitationis pro dec. eccl. s. Nicolai in_
- 3/1990 `supplic.`: gold **supplicante**, system **supplicatione** (step 4 (normalized)) -- _castro Halberstad. dioc. m. supplic. Sigismundo Rom. et Vng._
- 3/1990 `incorp.`: gold **incorporationis**, system **incorporare** (step 2 (candidates)) -- _Rom. et Vng. rege incorp. maioris preb. eccl. s._
- 3/1990 `d.`: gold **dicte**, system **datum** (step 2 (candidates)) -- _n. o. statut. eccl. d. 5 ian. 1415 L_
- 4/277 `A.`: gold **Aldenburg**, system **A.** (None) -- _s. Georgii in castro A. Nuemburg. dioc. in colleg._
- 4/277 `A.`: gold **Aldenburg**, system **A.** (None) -- _magistra etc. mon. in A. o. Prem. Trever. dioc._
- 4/1168 `B.`: gold **Besekow**, system **B.** (None) -- _eccl. b. Marie op. B. Misnen. dioc. de indulg._
- 4/1307 `expect.`: gold **expectatione**, system **expectativa** (step 2 (candidates)) -- _dioc. de can. sub expect. preb. Nuemburg. necnon s._
- 4/1307 `utr.`: gold **utroque**, system **utrius** (step 2 (candidates)) -- _cler. Magunt. dioc. ex utr. de mil. gen. de_
- 4/1307 `gen.`: gold **genere**, system **generalis** (step 2 (candidates)) -- _ex utr. de mil. gen. de benef. s. e._
- 4/1399 `ap.`: gold **apostoli**, system **apostolici** (step 4 (normalized)) -- _Marie conceptionis Anne Andree ap. ac omn. SS. in_
- 4/2980 `Nuremberg.`: gold **Nurembergensis**, system **Nuremberge** (step 3 (mined)) -- _Brandenburg. elector ac burggravius Nuremberg. de insigniis pont. pro_
- ...
