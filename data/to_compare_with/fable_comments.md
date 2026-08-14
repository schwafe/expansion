# Claude's comments per RG entry

Every remark Claude made about a **specific** entry in the two conversations *Expanding with Fable* (3–7 July 2026) and *Expanding abbreviations in Reportorium Germanicum texts* (31 July – 7 August 2026), sorted by RG volume and number. Batch-wide conventions that apply to no single entry are collected in the [general section](#general-conventions-and-batch-wide-notes) at the end.

Comments are quoted in Claude's own wording, trimmed to the relevant sentence(s). Source tags: **[F]** = *Expanding with Fable*, **[R]** = *Expanding abbreviations in Reportorium Germanicum texts*, followed by the date. Where a reference in the original was indirect ("the Görlitz fire notice", "the Busso entry", "supradd. mon."), the entry was identified by matching the quoted abbreviation against `ablaesse_texts.csv`.

---

## Volume II

### RG II 370 — Albertus aep. etc. Magdeburg et cives civ. Magdeburg.

- "post o. Benedicti abb." — here "o." is *obitum* (after the *death* of Abbot Benedict), not *ordinis*; the raid on his lodgings only makes sense after his death. The date "22 iuri. 97" is corrupt (presumably *iun.* or *iul.* in the print); I left it untouched. Also, "aep. Magunt." in the last sentence is expanded as plural, *archiepiscopos Maguntinos*, since Ludwig and Adolf were the rival claimants to Mainz. The final sentence breaks off mid-list in your source (ending with "comite,"), and I preserved that as-is. — **[F]** 3 Jul
- "m. evoc." / "m. assign." / "revoc. m.": expanded as *mandatum evocandi*, *mandatum assignandi*, *revocatio mandati de ... evocandis*, following the curial formula, with the dependent names adjusted to the required cases (accusative after *evocandi*, ablative after *de*). — **[F]** 3 Jul
- *(German translation)* The corrupt date "22 iuri. 97" is carried over with "(wohl Juni oder Juli)", and the final sentence ("Albert ... das Zeugnis über den Krieg...") is grammatically incomplete in the source — the translation marks the missing verb with "(legt vor?)" and notes that the text breaks off. — **[F]** 3 Jul

### RG II 913 — Brunswic

- Fourth entry: I left the cluster "publ. constit. ... fact." unexpanded. "Constit." is clearly the constitution *Provide attendentes* of Boniface VIII, but whether "publ." stands for *publicetur*, *publicent*, or a participle determines the case of both *constitutio(nem)* and *fact(a/am)*, and the sentence (with its stray quotation marks, likely OCR damage) doesn't settle it. A plausible reading is "mandatum, ut ... publicetur constitutio 'Provide attendentes' ... facta," but I didn't want to commit that to the file. — **[F]** 3 Jul
- *(German translation)* In RG II 913 I made the elliptical fourth entry readable by supplying "(aufgetragen)" in parentheses; the Latin leaves the construction around "publ." open, as flagged earlier. — **[F]** 3 Jul

### RG II 916 — Budissin

*Felix submitted his own expansion of this entry and asked whether the Latin was correct. Claude's corrections:*

- "7 maior 1402" — *maior* means "greater/larger"! The month May is *maius*, and dates take the genitive: **7. maii 1402**.
- "29 decembre 1401" — *decembre* is French/Italian, not Latin. The genitive is **decembris**.
- "13 ianuarius 1402" — nominative instead of genitive; it should be **ianuarii**. (In the RG itself the month names are usually just left abbreviated: mai., dec., ian. — that's also a safe option.)
- "ecclesia sancti Petri oppidum Misnen. diocesis" — *oppidum* can't stand in the nominative here. The church is *of the town* of Budissin, so it must be genitive: **ecclesia sancti Petri opidi (Budissin) Misnensis diocesis**. Note also that the RG normally spells it *opidum* with one p.
- "Misnen." is still unexpanded — it should be **Misnensis** (agreeing with *diocesis*).
- "beatae Marie" mixes classical orthography (*beatae* with -ae) and medieval orthography (*Marie* with -e). The RG uses the medieval forms consistently, so write **beate Marie**.
- "de interdicto loco" is grammatically possible, but the usual curial formula runs **de loco interdicto** (or *de locis interdictis*); check what the abbreviation in your source actually was — if it was "de loc. interd.", the word order should follow the formula.

— **[F]** 3 Jul

### RG II 2411 — Wilhelmus marchio Misnen.

*Felix submitted his own expansion; Claude found "quite a lot to fix", the recurring problems being (a) month names left in the nominative instead of the genitive, (b) nouns left in the nominative where the syntax requires genitive, dative, or ablative — "you can't just expand the abbreviation into its dictionary form, the case has to fit the sentence" — and (c) a few gender mistakes.*

- **Line 1:** "omnia monasterium monialis" → **omnia monasteria monialium** (neuter plural + genitive plural: all convents *of nuns*). "ordo sancte Clare" → **ordinis sancte Clare** (genitive of the order). "28 augustus" → **28. augusti**.
- **Line 2:** After *concessio* everything granted stands in the genitive: "concessio ius patronatus 4 canonicorum et prebenda maior" → **concessio iuris patronatus 4 canonicatuum et prebende maioris**. Note also that the grant was almost certainly of four *canonries* (canonicatuum), not four canons (canonicorum) — check whether your source had "canonic." "in ecclesia Misnen. in castro Misnen." → **in ecclesia Misnensi in castro Misnensi**. "12 december" → **decembris**.
- **Line 3:** "abbatibus monasterium Antiquecelle et monasterium Buech Cist. ordo" → **abbatibus monasteriorum Antiquecelle et Buech Cisterciensis ordinis**. "26 februarius" → **februarii**.
- **Line 4:** "cum decanatus et canonici" → **cum decanatu et canonicis** (ablative after *cum*). The middle of the sentence has collapsed: it should read roughly **et concessio dicto collegio parrochialis ecclesie beate Marie dicti loci ad ecclesiam Misnensem pertinentis** — the college (dative) receives the parish church (genitive), which *belonged* (participle *pertinentis*, not infinitive *pertinere*) to the church of Meissen. Then: "marchio donavit ecclesia Misnen. ius patronatus parochialis ecclesia in Ebirspach... dicti diocesis" → **marchio donavit ecclesie Misnensi ius patronatus parrochialium ecclesiarum in Ebirspach et sancti Nicolai in Friberg dicte diocesis** — *ecclesie Misnensi* dative (recipient), the churches in the genitive plural, and *diocesis* is feminine, so **dicte** diocesis, never "dicti". "1 december" → **decembris**.
- **Line 5:** "permutationis factus" → **permutationis facte** (feminine). "Mechtildem abbam" — *abbam* would be a male abbot (and misformed at that); an abbess is **abbatissam**. "monasterium Throni" → **monasterii Throni**. "de iure patronatus parochialis ecclesia in Turgaw" → **...parrochialis ecclesie in Turgaw**; "et de parochialis ecclesia in Novacuria" → **et de parrochiali ecclesia in Novacuria** (ablative after *de*). Again **dicte diocesis** twice.
- **Line 6:** "licentia electionis confessoris" is grammatical but not the curial formula; the standard expansion of "lic. elig. confess." is **licentia eligendi confessorem**. "31 martius" → **martii**.
- **Line 7:** "reliquia... collocata visitant" — *reliquie* is feminine plural, and it's the object of *visitant*: **reliquias in ecclesia Misnensi ab ipsis collocatas visitant**. "22 november" → **novembris**.
- **Line 8:** "in choro ecclesia Misnen." → **in choro ecclesie Misnensis**. "7 februarius" → **februarii**. (*ad altare... fundatum* is fine.)

— **[F]** 3 Jul

- *(when the entry came up again inside a CSV batch)* This is the entry we already worked through together, so I applied our corrected expansions (*canonicatuum*, *abbatissam*, *pertinentis*, *dicte diocesis*, *licentia eligendi confessorem*, etc.). One difference from before: the source itself reads "reliquia ... collocata" unabbreviated — since medieval Latin does use *reliquia* as a neuter plural variant, I left the source wording untouched rather than emending it to *reliquias ... collocatas*. — **[F]** 3 Jul
- *(German translation)* The exchange with the abbess of Nimbschen is translated as a swap of the Torgau patronage *against* the church in Novacuria ("gegen"), which is what a *permutatio* between two parties implies, though the Latin just coordinates the two objects with "et ... de". — **[F]** 3 Jul

### RG II 2477 — Hadmersleve

- "s. Marci Venet." → *sancti Marci Venetiarum* (elsewhere the same church appears as *de Venetiis*, as in RG 3412, where I kept the spelled-out form). — **[F]** 3 Jul

### RG II 2495 — Hamburg

- In the third entry I left "Wismer." unexpanded — it could be the uninflected place name or an adjective (*Wismariensis*), and the abbreviation doesn't decide it. "al." → *alias*. — **[F]** 3 Jul

### RG II 3412 — Hildesleve

- The church of St Mark appears here as *de Venetiis* spelled out; the spelled-out form was kept (cf. RG II 2477). — **[F]** 3 Jul

### RG II 5209 — Issleve

- "X mil. martirum" is the feast of the Ten Thousand Martyrs, so *X milium martirum*; "bb. XII ap." → *beatorum XII apostolorum*; "fr. kalend." is a Kalandsbruderschaft, so *confraternitas fratrum kalendarum*. — **[F]** 3 Jul

### RG II 6133 — Novacella (Neuzelle)

- "duci Sagan." → *duci Saganensi*; "mon. Luben." → *monasterium Lubense*, i.e. Leubus/Lubiąż, which fits the Cistercian order and Wrocław diocese; "sup. concordia ... fact." → *super concordia ... facta* (ablative). In the third entry "par. eccl." covers four churches, hence *parrochialium ecclesiarum*. — **[F]** 3 Jul

### RG II 6177 — Osterborkch (Osterburg)

- Third entry: "al. d. Schymming" → *alias dicto Schymming*, in the ablative agreeing with *ab Henrico de Soltwedel ... preposito*; "est fund." → *est fundatum* (neuter, agreeing with *altare*). Note the entry is really two sentences run together ("...Verdensis diocesis | altare ab Henrico..."); I preserved the source's punctuation-less join rather than inserting a semicolon. — **[F]** 3 Jul

### RG II 7276 — Tribuzes

- "eccl. Aquileg." → *ecclesie Aquilegensis* (genitive, parallel to *ecclesie sancte Marie Magdalene* after *ad instar*). — **[F]** 3 Jul

### RG II 7601 — Wittenberg

- "eccl. capella omn. SS. nunc." → *ecclesia capella omnium Sanctorum nuncupata* — "nunc." is the standard curial formula *nuncupata* ("the church called the All Saints' chapel," i.e. the Wittenberg Allerheiligenkapelle), not the adverb *nunc*. — **[F]** 3 Jul

### RG II 7829 — Dresden

- "p." here is the preposition *per* (*per priorem provincialem ... construenda* — the church to be built by the provincial prior), unlike in the earlier Aldenburg entry where "m. arg. p." was *marcarum argenti puri*. — **[F]** 3 Jul

---

## Volume III

### RG III 228 — Aldenburg

- I preserved the stray punctuation in "L 185 278v. ." as in your source. — **[F]** 3 Jul

### RG III 1990 — Tangermunde

- The long third entry required several case-sensitive expansions: "in colleg. eccl. fecerat constit." → *in collegiatam ecclesiam fecerat constitui*; "cum par. eccl. ... incorp. ... spect." → ablatives after *cum* (*incorporata*, *spectante*); "super prepos." → *super prepositura* (ablative — the accusative *preposituram* would also be defensible); "iuris instit. prep. et can." → *iuris instituendi prepositum et canonicos*. In the fourth entry, "m. supplic. Sigismundo ... rege" is an ablative absolute (*supplicante Sigismundo Romanorum et Vngarie rege*), and "n. o. statut. eccl. d." → *non obstantibus statutis ecclesie dicte*. — **[F]** 3 Jul
- I preserved the spelling "exemtione" and capitalized "Visitationis" as in your source. — **[F]** 3 Jul

### RG III 2188 — Wittenberg

- I preserved the two-digit year "17 oct. 11" as in your source. — **[F]** 3 Jul

---

## Volume IV

### RG IV 277 — Aldenburg

- "ref." → *reformatio*, the supplication type; if your project's abbreviation key resolves it differently, this is easy to search-and-replace. — **[F]** 3 Jul
- The single-letter headword abbreviation "A." → *Aldenburg*. — **[F]** 3 Jul

### RG IV 1168 — Besekow

- The single-letter headword abbreviation "B." → *Besekow*. — **[F]** 3 Jul

### RG IV 1253 — Burghartzwalde

- I preserved the space before the colon as in your source. — **[F]** 3 Jul

### RG IV 1307 — Busso de Vicedominis

- I left **"s. e. p." unexpanded** in both occurrences ("de beneficio s. e. p. pro ..."). It's clearly a fixed formula qualifying the requested benefice, but I'm not certain which one, and guessing would risk corrupting the record. The rest is standard: "de can. sub expect. preb." → *de canonicatu sub expectatione prebende*, and "ex utr. de mil. gen." → *ex utroque de militari genere* (of knightly descent on both parents' sides). — **[F]** 3 Jul
- *(German translation)* The two "Benefizium **s. e. p.**" remain untranslated, as in the Latin expansion. — **[F]** 3 Jul

### RG IV 1399 — Catherina marchionissa Misnen. (Colditz altar)

- *(German translation)* In the Colditz altar entry the patrocinium list "b. Marie, conceptionis Anne, Andree ap." is oddly punctuated in the source; I translated it item by item ("der seligen Maria, der Empfängnis, der Anna, ..."), but it could also be meant as "der Empfängnis (Mariens durch) Anna" — the Latin doesn't settle it. — **[F]** 3 Jul

### RG IV 2980 — Fridericus marchio Brandenburg. elector ac burggravius Nuremberg.

*"The long Friedrich of Brandenburg entry is where the judgment calls sit."*

**Left unexpanded (uncertain):**

- "c. iuribus **pres.**" — the fief purchase from Count Oswald of Truhendingen came "with rights of pres..." — presumably presentation rights (*presentationum* or *presentandi*), but the exact form isn't determinable, so I expanded only *cum iuribus* and kept "pres."
- "**conf.** remissionem debitorum ... concessam" (the Nauen? line) — here the accusative object shows "conf." works as a verb ("[the pope] confirms the remission of debts..."), not the nominal *confirmatio* used elsewhere; since the intended form (*confirmat*, *confirmatur*...) isn't certain, I left it. The rest of that line is expanded, including "p. d. F." → *per dictum Fridericum*.
- "op. **Nouwen. ?**" — the question mark is the RG editors' own uncertainty about the place (Nauen?); preserved as-is.
- "**H.** card. s. Eusebii legatum" — expanded the case (*per H. cardinalem sancti Eusebii legatum*) but kept the initial, though this is identifiable as Henry Beaufort, cardinal of S. Eusebio and legate in Germany 1427/28.
- "**PK n. 112/114.**" — a literature citation, untouched.

**Other decisions worth knowing:**

- Headword-referential initials expanded as before: "pro **J.**" → *pro Johanne* (the margrave's son, three times in the 1429 line).
- "**Noveciv./Vetericiv.** Brandenburg." → *Novecivitatis/Vetericivitate Brandenburgensi(s)* — the Neustadt and Altstadt of Brandenburg an der Havel; accordingly "ss. Katherine et Amalberge" → *sanctarum* (both female saints).
- "de **confess.**" standing alone → *de confessionali* (the confessional letter), distinct from "lic. el. confess." → *licentia eligendi confessorem*.
- "**excom.**" in both "post expulsionem" and "post recessum" → *excommunicatorum*.
- "supradd. mon." → *supradictorum monasteriorum*; "abba." → *abbatissa* (RG IV's regular siglum); "ref. conc. ingr." → *reformatio concessionis ingrediendi* (matching the *licentia intrandi* granted the same day); "de conf. privil." → *de confirmatione privilegiorum*, where singular *privilegii* would also be possible.
- In "de conf. indulti ... **domo** o. f. m. Brandenburg." the unabbreviated "domo" is kept even though a dative *domui* would be expected — I only expanded the surrounding words (*domo ordinis fratrum minorum Brandenburgensi*).

— **[F]** 3 Jul

- *(German translation)* Carried-over uncertainties: "mit den Rechten der **pres.** (Präsentation?)" in the Truhendingen fief purchase, the initial "H." for the cardinal legate of S. Eusebio (Heinrich Beaufort), and the literature citation "PK n. 112/114." — and "Nouwen. ?" with the RG editors' question mark (vermutlich Nauen). Identifications used in this entry: Heilsbronn (Fons salutis), Walderbach, Wülzburg, Schwabach, Blaufelden, Crailsheim, Langenzenn, das Klarissenkloster Hof ("curia Regnitz"), Himmelkron ("Corona celi"), Wöhrd bei Nürnberg (villa Werd) und Kulmbach. — **[F]** 3 Jul

### RG IV 3100 — Fridericus sen. marchio Misnen.

- Left unexpanded: "benef." in "super collatione benef.". — **[R]** 31 Jul
- The odd "dus Saxonie" rendered as "dux Saxonie" (the 1423 date fits Friedrich's elevation exactly). — **[R]** 31 Jul

### RG IV 3705 — Godebusse

- "hosp." read as plural where several institutions are listed (*hospitalia* in Godebusse). — **[R]** 31 Jul

### RG IV 8386 — Johannes Mentz Menss scobator palatii ap.

- Left unexpanded, since the resolution isn't certain: "tab." and "assig. pecunia". — **[R]** 31 Jul

### RG IV 14862 — Wilhelmus lantgravius Thuringie et marchio Misnen.

- Left unexpanded: "et C." after "ordinis sancti Benedicti". — **[R]** 31 Jul

---

## Volume V

### RG V 885 — Brunswic Brunswicen. Halberstad. et Hildesem. diocc.

*The first text of the Fable conversation, pasted directly into the chat rather than sent as CSV. Claude identified it as "clearly a Repertorium Germanicum–style calendar of papal registers, so the standard curial formulas apply".*

- **Expanded with confidence:** s./ss. = sancti/sanctorum; B. = Brunswic (the headword place); dioc./diocc. = diocesis/diocesium; par. eccl. = parrochialis ecclesia; o. s. Ben. = ordinis sancti Benedicti; univ. op. = universitas opidi; m. arg. = marcarum argenti; de n. evocando = de non evocando (the well-known privilegium de non evocando); R.I. = Romanorum imperatore (Sigismund had been crowned emperor in 1433, so "rege" is excluded for 1436); conc./conf. = concessi/confirmati (agreeing with privilegii); d. = dicte; exec. = executores; dec./decc. = decanus/decani; capit. = capitulum; supplic. = supplicante/supplicantibus (ablative absolute, singular for Ludolph, plural for the dukes).
- **Left unexpanded:** the register sigla and citations (S = Supplikenregister, L = Lateranregister volume numbers; r/vs/vss = recto, verso [et sequens/sequentes] — these are archival references, not Latin words to be resolved in the text), the dates, and the doublet "Woden Weden", which looks like two spelling variants of the place name as given in the source.
- **Minor caveats:** the grammatical case in the first entry ("abbas et monasterium" nominative) follows the usual RG headword convention but is not marked in the abbreviation itself; and "Maguntine" follows the standard curial form *Maguntina diocesis*, though "Maguntinensis" also occurs — this is the one expansion where a variant form is genuinely possible.

— **[F]** 3 Jul

### RG V 1954 — Fredericus dux Saxonie et marchio Misnen.

- One point worth flagging: in "etiam pro ux. et fam." I expanded to the plural "pro uxoribus et familiaribus" since the grant covers both dukes (Fredericus and Sigismundus); if the privilege was formally issued to each individually, the singular "uxore" would also be defensible. — **[F]** 3 Jul
- In V 1954 I did expand "cass. s.d." → "cassatum sine data", which is the normal use. — **[R]** 31 Jul

### RG V 2286 — Gerlitz Gorlicz Misnen. dioc. (Görlitz)

- Left unexpanded: "s.d." in the Görlitz fire notice — here it precedes a date, so it can't be the usual "sine data"; possibly "sub die". — **[R]** 31 Jul
- "hosp." read as plural where several institutions are listed ("capelle in hospitalibus" in Görlitz). — **[R]** 31 Jul

### RG V 3472 — Hestede Halberstad. dioc.

- Left unexpanded: "s.p.d.". — **[R]** 31 Jul

### RG V 6853 — Misnen.

- The headword line itself was kept as printed ("Misnen."); only the appended "…dioc." formulas were expanded. — **[R]** 31 Jul

### RG V 7372 — Nuemburg. Nuemburg.

- Left unexpanded, because I couldn't be certain of the word or its form: *Magunt.* (Maguntinus vs. Maguntinensis) and *extra muros Nuemburg.* — **[R]** 31 Jul
- Interpretive point: I rendered "n. can. et preb. p. scolast. sed scolastr. p. can. prebend." as "non canonicatus et prebende per scolasticum sed scolastria per canonicos prebendatos" (scholaster vs. scholastry). — **[R]** 31 Jul
- The headword line itself was kept as printed ("Nuemburg. Nuemburg."). — **[R]** 31 Jul

### RG V 7397 — Osnaburg.

- Left unexpanded: *l.b.* and the adjacent *dec. Osnaburg.*; also *sustentari val.* (tense ambiguous). — **[R]** 31 Jul

### RG V 8486 — Sunden. Zwerin. dioc.

- The headword line itself was kept as printed ("Sunden."). — **[R]** 31 Jul

### RG V 9465 — Wilsnacen. Wilczenach Havelberg. dioc.

- Left unexpanded: *supplic.,* in the lemma sentence (supplicat vs. supplicantis). — **[R]** 31 Jul
- The headword line itself was kept as printed ("Wilsnacen. Wilczenach"). — **[R]** 31 Jul

---

## Volume VI

### RG VI 568 — Brandenburg.

- Interpretive point: I took "in d. eccl." as plural ("in dictis ecclesiis"), since the entry concerns both the Brandenburg and Havelberg cathedral churches. — **[R]** 31 Jul
- The headword line itself was kept as printed ("Brandenburg."). — **[R]** 31 Jul

### RG VI 5255 — Stendalia

- Left unexpanded: the sigla-like *T.* in "Non est honesta T." — **[R]** 31 Jul

### RG VI 5322 — Tangermunda

- Left unexpanded: *exemptio iudic.* — **[R]** 31 Jul

---

## Volume VII

### RG VII 432 — Choryn

- "de transf. capel. ... devastatam" rendered as gerund "de transferendo capellam ... devastatam" (the accusative *devastatam* rules out *translatione* + genitive). — **[R]** 7 Aug
- "ss. Marie Magdalene et Brigitte" → *sanctarum* (female saints). — **[R]** 7 Aug

### RG VII 1083 — Hermannus Piwerling cler. Halberstad. dioc.

- Left unexpanded and worth flagging: "Stendal." in "op. Stendal." — could be the bare place name or *Stendaliensis*. — **[R]** 7 Aug
- "perp. s. c. vicar." → *perpetuis sine cura vicariis*. — **[R]** 7 Aug
- "can. et preb. litig." → *canonicatu et prebenda litigiosis* (litigious, not the verb). — **[R]** 7 Aug

---

## Volume VIII

### RG VIII 547 — Brunswic. Brunßwic., Brunswicen.

- "conc." → *concesserunt* (finite verb with Boniface IX, Sigismund and Martin V as subjects). — **[R]** 7 Aug

### RG VIII 2974 — Johannesabb. etc. mon. \<s. Nicolai\> in Grunenhain

- The run-together "Johannesabb." kept glued as "Johannesabbas" to preserve the printing quirk. — **[R]** 7 Aug

### RG VIII 4669 — Nuemburg.

- Left unexpanded: "Magunt." (as in previous batches). — **[R]** 7 Aug
- The editor's query "[dioc.?]" kept verbatim. — **[R]** 7 Aug

### RG VIII 5719 — Uszleuben

- Left unexpanded: "nom." in "de indulg. nom." — unclear whether *nominatim* or something else. — **[R]** 7 Aug

---

## Volume IX

### RG IX 730 — Colditz Colnitz

- The editorial mark "< Margerite>" preserved with its leading space. — **[R]** 7 Aug

### RG IX 1004 — Deben

- "appl." → *apostolorum* (from the medieval apl̄- contraction). — **[R]** 7 Aug

### RG IX 1746 — Halla Alle

- "m." before the V-reference → *mandatum*. — **[R]** 7 Aug
- The source's own dangling "Prepositus ... diocesis ." paragraph was preserved, as was the editorial "[Petrum]". — **[R]** 7 Aug

### RG IX 1835 — Henricus Bentzin Bontzin rect. par. eccl. s. Jacobi Rostockcen.

- "vacat. p. resign." → *vacatura per resignationem* (future vacancy); "vac. p. dim." → *vacantibus per dimissionem*; "de confic. litt." → *de conficiendis litteris*. — **[R]** 7 Aug

### RG IX 2155 — Henricus com. in Stolberg et dom. temporalis loci in Werningerode

- Left unexpanded and flagged: "Magunt." (including "Magunt. [!] dioc." in this entry) and "cap." in "3 partes rectori et 27 suo cap." — could be *capellano* or *capitulo*, and the following "vicariis et choralibus" doesn't settle it. — **[R]** 7 Aug
- The editorial "[dioc.]" without a query mark expanded to "[diocesis]" (unlike "[dioc.?]" last time, which I kept because of the editor's own uncertainty). — **[R]** 7 Aug
- "pro par. eccl. op. Stalberge, Heringen et Kelebra" rendered plural as "pro parochialibus ecclesiis opidorum...". — **[R]** 7 Aug

### RG IX 5330 — Pritzwalk

- "auct. ordin." → *auctoritate ordinaria* (the stock phrase, rather than "of the ordinary"). — **[R]** 7 Aug

### RG IX 5702 — Temptzyn

- The source's own duplication (the repeated "domus sancti Antonii...") was preserved. — **[R]** 7 Aug

---

# General conventions and batch-wide notes

Remarks that apply to a whole batch rather than to one entry, in the order they were made.

## [F] 3 Jul — CSV batch 1 (RG II 370, 645, 878, 913, 916)

No batch-wide conventions were stated beyond the entry notes above.

## [F] 3 Jul — CSV batch 2 (RG II 919 – 5711, 20 entries)

- All 20 entries are expanded in the same CSV format.

## [F] 3 Jul — CSV batches 3 and 4 (RG II 6133 – 7276; RG II 7448 – 7829)

- Only entry-specific remarks; no new global conventions.

## [F] 3 Jul — CSV batch 5 (RG III 171 – 2195, RG IV 277 – 1307, 14 entries)

- The volume 3/4 conventions ("capel.", "de indulg.", the S/I register sigla) posed no problems.

## [F] 3 Jul — German translation of RG II 370 – 7276 (30 entries)

- **Place names:** where the identification is standard I used the modern German form (Braunschweig, Bautzen, Aschersleben, Görlitz, Eisleben, Lauban, Neuzelle, Osterburg, Tempzin, Tribsees, Altzelle, Nimbschen, Torgau, Ebersbach, Freiberg, Krevese, Ritzebüttel, Leubus, Breslau, Sagan). Unidentified or ambiguous names stay in the source spelling (Boldensberg, Ernfridestorff, Grevenhayn, Hesewik, Hildesleve, Idelenstede, Lynpuhel, Lovenborch, Madela, Muchele, Netekendorp, Fortinberg, Besecow, Funfechin, Welmenitz, Esterhusin, Closterberche). For "Novacuria" I kept the Latin with "(Neuhof)" as a gloss, since several places of that name exist.
- **Terminology:** I rendered the curial grace types in the usual German diplomatics vocabulary — *conservatoria* → Konservatorie (Schutzbrief), *altare portatile* → Tragaltar, *indulgentia ad instar* → Ablass nach dem Vorbild von..., *de non evocando* left in Latin with a gloss, since it's a technical term. *Ecclesia maior* in Magdeburg is rendered as Domkirche.

## [F] 3 Jul — German translation of batches 4–6 (30 entries)

- **Identifications used:** Altzelle, Zehdenick, Königslutter (Regali Lutter), Zwickau, Altenburg, Cottbus, Döbeln, Herzberg, Wolfenbüttel, Beeskow, Roßla, Kaltenborn, Colditz. Uncertain or unidentified names stay in the source form: Villabuken, Monsboldensberg, Canewitz, Keentze, Baard, Kempnic (Chemnitz oder Kamenz), Ebrstorff, Vredeland, Burghartzwalde, Bretzen, Biele.
- **Terminology:** the recurring grace types are rendered consistently — *de confessionali* → Beichtbrief, *interdicto* → Interdikt(sindult), *ante diem* → (Messe) vor Tagesanbruch, *de lacticiniis* → Milchspeisen(dispens), *de mortis articulo* → (vollkommener Ablass) in der Todesstunde, *de fructibus in absentia* → Bezug der Einkünfte in Abwesenheit, *reformatio* → Reformatio (Neuausfertigung der Supplik). Words supplied for readability that have no counterpart in the elliptical Latin stand in parentheses.

## [R] 31 Jul — batch 1 (RG V 6319 – 9557, RG VI 126 – 6006, 27 entries)

- **What I expanded.** All standard RG abbreviations whose word and grammatical form were determinable from context: eccl. → ecclesia/ecclesie, par. → parochialis, dioc. → diocesis, d. → dictus (in the correct case/gender), s./b. → sanctus/beate, supplic. → supplicante/supplicantibus where the ablative construction was clear, conc. → concessum/concessit/concesserunt as syntax demanded, relax./ref./conf./decl./incorp./revoc. → the corresponding nouns, m. arg. p. → marcarum argenti puri, e.m. → extra muros, s.c. → sine cura, s.d. → sine data, p.o. → per obitum, R.I. → Romanorum imperator, month names in dates, and the diocesan adjectives in -en. (Misnen. → Misnensis, Halberstad. → Halberstadensis, etc., inflected per context). Numerals, archival sigla (S, L, V, T, DC) and folio references were left untouched, as were the bracketed editorial additions.
- **Left unexpanded generally:** the single-letter place initials (L., M., N., O., S., T., W., Cz.), which are lemma references rather than expandable abbreviations.
- **Orthography.** I used the medieval spellings consistent with RG practice: parochialis, presbiter, martiris; original spellings like "erigerunt", "redempcione" and the doubled variant name readings (Stoube Stoybe, etc.) were preserved unchanged.
- Row structure, entry order, and internal line breaks preserved exactly.

## [R] 31 Jul — batch 2 (RG IV 3100 – 15028, RG V 678 – 6313, 34 entries)

- Same column structure, paragraph breaks preserved, medieval orthography kept (presbiter, opidum, Saxsonie, dampna); digits, folio references, sigla (S, L, V, DC, A, M, IE, L0), editorial brackets [...] and <...>, name doublets, single-letter place initials, and the "!" sic-marks all left untouched.
- Vol. IV dates appear without the day-period ("7 maii 1418"), vol. V dates with it ("12. septembris 1437"), matching each volume's own style.
- Left unexpanded again: "Magunt." (Maguntinus vs. Maguntinensis, as before).
- Standard grace lists rendered as "de remissione plenaria; altari portatili; interdicto; ante diem; confessionali" (standalone grants as nominatives: interdictum, confessionale, remissio plenaria); "e. op." → "extra opidum"; "can. s. e. preb." → "canonicatibus sub expectatione prebendarum"; "conc. privil. fam." → "concessio privilegiorum familiarium"; "conc. de 7/5 an." → "concessum de 7/5 annis".

## [R] 7 Aug — batch 3 (RG VII 432 – 2510, RG VIII 324 – 5760, 15 entries)

- Structure, paragraph breaks, sigla (S, L, V, I), folio references with their trailing periods ("112rs.", "41v-43r"), the spaced " : " and " , " punctuation of these volumes, editorial brackets, name doublets, and single-letter place initials are all preserved, as are the volume-specific date styles (vol. VII "9 aprilis 1457" without day-period, vol. VIII "4. novembris 1458" with it). The capitalized entry openings of these volumes ("Abbas etc.", "Parochialis ecclesia...") are kept.
- Newly recurring formulas expanded consistently: "relax. 7 an." → "relaxatio 7 annorum", "fiat ad/de X an." → "fiat ad/de X annos/annis", "s. d." → "sine data", "R. I. / R. R. / S. R. I." → "Romanorum imperator / Romanorum rex / sacri Romani imperii", "ex utr. par. de mil. gen." → "ex utroque parente de militari genere", "supplic. + ablative" → "supplicante/supplicantibus", "pres. in cur." → "presente in curia", "m. arg." → "marcarum argenti".
- Headword forms in lemma lines left unexpanded ("Brunswic. Brunßwic., Brunswicen.", "Nuemburg.", "Asscherleven.").

## [R] 7 Aug — batch 4 (RG IX 419 – 6302, 19 entries)

- The volume's characteristic features are preserved: capitalized entry openings, day-period dates ("3. ianuarii 1469"), the occasional double spaces before dates and sigla, trailing " ." spacings, editorial marks ("[!]"), name doublets.
- Recurring vol.-IX formulas expanded consistently: "supplic. + ablative" → "supplicante/supplicantibus" (plural where several supplicants are named), "Fiat/Conc. de X an." → "Fiat/Concessum de X annis", bare "Fiat/Conc. X an." → "X annorum", "s.c." → "sine cura", "de iur. patron. laic." → "de iure patronatus laicorum", "o.s. Aug./o. fr. min./o. Prem." → the full order names, "R.E." → "Romane ecclesie", "horas can." → "horas canonicas".

---

# Coverage

Entries processed in the two conversations that drew **no** entry-specific comment (should be the rest of ablaesse_texts.csv except for Volume X):

- **Vol. II:** 645, 878, 919, 1462, 1596, 1682, 2229, 2322, 3398, 3604, 5321, 5329, 5332, 5439, 5443, 5697, 5711, 6248, 6985, 7272, 7448, 7530, 7567, 7568, 7645
- **Vol. III:** 171, 535, 556, 1008, 1629, 1969, 2195
- **Vol. IV:** 1309, 1318, 1415, 1421, 2363, 2521, 2962, 3683, 3706, 3877, 5597, 5759, 5813, 6189, 6193, 6709, 10237, 10238, 10240, 10537, 11033, 11069, 11967, 12022, 13431, 14897, 15028
- **Vol. V:** 678, 981, 1482, 1601, 2472, 6313, 6319, 6338, 8363, 8513, 8895, 9494, 9557
- **Vol. VI:** 126, 427, 554, 921, 922, 1073, 3976, 4628, 5229, 5915, 6002, 6006
- **Vol. VII:** 2477, 2487, 2510
- **Vol. VIII:** 324, 1132, 4104, 4732, 5423, 5760
- **Vol. IX:** 419, 528, 589, 597, 1057, 3474, 4226, 5381, 5679, 5684, 6104, 6302
