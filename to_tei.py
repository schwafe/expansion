#!/usr/bin/env python3
"""
Step 6: the final output -- one TEI document that holds both readings.

The workflow produces one CSV per stage, each a complete text in which the
abbreviations have been replaced. That loses the RG's own reading: once
`eccl.` has become `ecclesiae` there is no way back to the source. This script
writes the two readings into a single TEI P5 document instead, so a consumer
can take either one:

    <choice><abbr>eccl.</abbr><expan resp="#step1 #step4">ecclesiae</expan></choice>

    the RG's reading  = drop the <expan> of every <choice>  (`readings()[0]`)
    the expanded text = drop the <abbr> of every <choice>   (`readings()[1]`)

An <abbr> that stands outside a <choice> is an abbreviation nobody resolved and
belongs to both readings, which is why the rule names <choice> rather than the
elements alone.

`@resp` names the step that decided the expansion, so the rule-based expansions
can be told from the model-chosen ones without re-running anything; the steps
are declared in the teiHeader. An abbreviation the pipeline never resolved is a
bare <abbr> with no <expan> -- present in both readings and easy to list.

The pairing of abbreviation and expansion reuses the alignment of `evaluate.py`:
the abbreviated source is aligned with the expanded text at word level, which
works because the expansion steps only ever replace abbreviations. Three things
that alignment does not settle have to be decided here, because the markup has
to reproduce the source character for character rather than token for token:

- Material *between* two words can differ (`aep.` -> `archiepiscopus,` adds a
  comma; `Rom. imp.` -> `Romanorum Imperatoris` changes the spacing). Where the
  source and the expansion disagree about it, that material is folded into the
  neighbouring <choice> so neither reading loses it.
- Not every word ending in a period is an abbreviation. A sentence-final word
  (`fecerunt.`) and a folio mark glued to a number (`236v.`) are plain text; a
  token only becomes a bare <abbr> if the glossary actually lists it.
- Where the alignment finds no expansion at all the abbreviation is left as
  plain source text and the regest is reported, never silently dropped.

Every regest is round-tripped before it is written: the two readings are parsed
back out of the markup and compared with the inputs. A regest whose source
reading is not reproduced exactly is refused, so the RG text cannot be corrupted
by a bug in here.

Usage:
    python to_tei.py            # dry run: report what would be written
    python to_tei.py --write    # write data/rg_expanded.xml
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import polars as pl

from evaluate import (DATA_DIR, REVIEW_DIR, SOURCE, STAGES, TOKEN, align,
                      build_anchor_index, is_abbreviation)

OUTPUT = DATA_DIR / "rg_expanded.xml"
REPORT = REVIEW_DIR / "tei_report.md"
GLOSSARY = (DATA_DIR / "glossary.csv",)

TEI_NS = "http://www.tei-c.org/ns/1.0"

# the xml:id of the responsibility statement for each stage
RESP_OF_STAGE = {
    "once": "step1",
    "twice": "step2",
    "thrice": "step3",
    "normalized": "step4",
}

# what the teiHeader says about each step. The model names are the MODEL
# constants of the notebooks that produced the stage -- keep them in sync with
# expanding_candidates.ipynb, expanding_rest.ipynb and normalizing.ipynb.
RESPONSIBILITY = [
    ("step1", "expansion by rule from the Abkürzungsverzeichnis", None),
    ("step2", "choice among the candidates of the Abkürzungsverzeichnis", "gemma-4-31b-it"),
    ("step3", "choice among candidates mined from the RG", "gemma-4-31b-it"),
    ("step4", "normalisation of the inflection", "gemma-4-31b-it"),
]

# punctuation an expansion may add without the source having it
PUNCTUATION = re.compile(r"[,;:]*")


# --------------------------------------------------------------------------
# the pieces a marked-up text is made of
# --------------------------------------------------------------------------

@dataclass
class Segment:
    """
    One piece of a marked-up text.

    `expan is None` means the piece reads the same either way (plain text or an
    abbreviation nobody expanded); otherwise `abbr` is the source reading and
    `expan` the expanded one.
    """

    abbr: str
    expan: str | None = None
    resp: str = ""
    kept: bool = False  # an abbreviation the pipeline did not resolve

    @property
    def plain(self) -> bool:
        return self.expan is None and not self.kept


def token_spans(text: str) -> list[tuple[str, int, int]]:
    """The tokens of a text with their character offsets."""
    return [(m.group(), m.start(), m.end()) for m in TOKEN.finditer(text)]


def known_abbreviations(*paths: Path) -> set[str]:
    """Every abbreviation the glossary lists, i.e. what may become an <abbr>."""
    known: set[str] = set()
    for path in paths:
        known |= set(pl.read_csv(path)["Abkürzung"].drop_nulls().to_list())
    return known


def is_shelfmark(tokens: list[tuple[str, int, int]], index: int) -> bool:
    """
    `236v.` -- a folio mark glued to a number, not an abbreviation. The
    tokenizer splits it into `236` and `v.`, so the giveaway is that the two
    tokens touch and the first one is a number.
    """
    if index == 0:
        return False
    previous, current = tokens[index - 1], tokens[index]
    return previous[2] == current[1] and previous[0].isdigit()


def attribute(
    index: int,
    abbreviation: str,
    stage_texts: dict[str, str],
    stage_tokens: dict[str, list[tuple[str, int, int]]],
    stage_spans: dict[str, list[tuple[int, int] | None]],
) -> str:
    """
    The `@resp` value: the step that first expanded the abbreviation, plus every
    later step that changed the expansion again. Same rule as
    `evaluate.attribute`, but it reads the characters rather than the tokens so
    the punctuation a step adds does not count as a change.
    """
    steps: list[str] = []
    previous = abbreviation
    for stage, text in stage_texts.items():
        span = stage_spans[stage][index]
        if span is None or span[1] <= span[0]:
            continue
        tokens = stage_tokens[stage]
        current = text[tokens[span[0]][1]:tokens[span[1] - 1][2]]
        expanded = not any(is_abbreviation(word) for word in current.split())
        if not steps and expanded:
            steps.append(RESP_OF_STAGE[stage])
        elif steps and current != previous:
            steps.append(RESP_OF_STAGE[stage])
        previous = current
    return " ".join("#" + step for step in steps)


def mark_up(
    source: str,
    stage_texts: dict[str, str],
    anchors: dict[str, set[str]],
    known: set[str],
) -> tuple[list[Segment], int]:
    """
    Split a source text into segments against the expanded text.

    `stage_texts` is ordered; the last stage is the reading that gets published,
    the earlier ones only serve the `@resp` attribution. Returns the segments
    and the number of abbreviations that could not be placed.
    """
    final = list(stage_texts)[-1]
    tokens = token_spans(source)
    stage_tokens = {name: token_spans(text) for name, text in stage_texts.items()}
    stage_spans = {
        name: align([t[0] for t in tokens], [t[0] for t in stage_tokens[name]], anchors)
        for name in stage_texts
    }
    target, target_tokens = stage_texts[final], stage_tokens[final]

    segments: list[Segment] = []
    unplaced = 0

    def gap(in_source: str, in_target: str) -> None:
        """
        The material between two units. Identical on both sides it is plain
        text; where it differs it belongs to the two readings separately and is
        folded into the preceding <choice> rather than dropped.
        """
        if in_source == in_target:
            if in_source:
                segments.append(Segment(in_source))
        elif segments and segments[-1].expan is not None:
            segments[-1].abbr += in_source
            segments[-1].expan += in_target
        else:
            segments.append(Segment(in_source, in_target))

    cut_source = cut_target = 0
    for index, (token, start, end) in enumerate(tokens):
        span = stage_spans[final][index]
        placed = span is not None and span[1] > span[0]
        begin = target_tokens[span[0]][1] if placed else cut_target
        stop = target_tokens[span[1] - 1][2] if placed else cut_target

        before = source[cut_source:start]
        gap(before, target[cut_target:begin])
        cut_source, cut_target = end, max(cut_target, stop)

        if not is_abbreviation(token) or is_shelfmark(tokens, index):
            segments.append(Segment(token))
            continue
        if not placed:
            if not before and segments and segments[-1].expan is not None:
                # glued to the abbreviation before it and sharing its expansion
                # (`s.p.d.` -> `sineperdatum`): one <choice>, not three pieces
                segments[-1].abbr += token
                continue
            # no expansion could be located: keep the source reading and count it
            segments.append(Segment(token, kept=token in known))
            unplaced += 1
            continue

        expansion = target[begin:stop]
        if expansion == token:  # the pipeline left it standing
            segments.append(Segment(token, kept=token in known))
            continue

        # punctuation the expansion introduced and the source does not have
        after_source = PUNCTUATION.match(source, end).group()
        after_target = PUNCTUATION.match(target, cut_target).group()
        if after_target and after_target != after_source:
            expansion += after_target
            cut_target += len(after_target)

        segments.append(
            Segment(token, expansion,
                    attribute(index, token, stage_texts, stage_tokens, stage_spans))
        )

    gap(source[cut_source:], target[cut_target:])
    return segments, unplaced


# --------------------------------------------------------------------------
# markup and the two readings
# --------------------------------------------------------------------------

def render(segments: list[Segment]) -> str:
    """The segments as TEI markup."""
    out = []
    for segment in segments:
        if segment.plain:
            out.append(escape(segment.abbr))
        elif segment.expan is None:
            out.append(f"<abbr>{escape(segment.abbr)}</abbr>")
        else:
            resp = f' resp="{segment.resp}"' if segment.resp else ""
            out.append(
                f"<choice><abbr>{escape(segment.abbr)}</abbr>"
                f"<expan{resp}>{escape(segment.expan)}</expan></choice>"
            )
    return "".join(out)


def readings(markup: str) -> tuple[str, str]:
    """
    The two readings of a marked-up text: (abbreviated, expanded).

    This is the consumer side of the format, and it is what the round-trip check
    uses -- the markup is parsed, not string-matched, so a reading can only come
    out right if the markup is genuinely well formed.
    """
    root = ElementTree.fromstring(f"<p>{markup}</p>")

    def walk(element, keep: str) -> str:
        drop = "expan" if keep == "abbr" else "abbr"
        text = element.text or ""
        for child in element:
            # only a <choice> offers two readings; a bare <abbr> is in both
            if not (element.tag == "choice" and child.tag == drop):
                text += walk(child, keep)
            text += child.tail or ""
        return text

    return walk(root, "abbr"), walk(root, "expan")


def element(tag: str, text: str, **attributes) -> str:
    marked = "".join(f' {name.replace("_", ":")}="{escape(value)}"'
                     for name, value in attributes.items())
    return f"<{tag}{marked}>{text}</{tag}>"


def header() -> str:
    """The teiHeader, including what each step did and which model did it."""
    statements = "\n".join(
        f'   <respStmt xml:id="{ident}"><resp>{escape(what)}</resp>'
        + (f"<name>{escape(who)}</name>" if who else "")
        + "</respStmt>"
        for ident, what, who in RESPONSIBILITY
    )
    return f"""\
 <teiHeader>
  <fileDesc>
   <titleStmt>
    <title>Repertorium Germanicum: Ablässe, with the abbreviations expanded</title>
   </titleStmt>
   <publicationStmt><p>Akademie der Wissenschaften zu Göttingen</p></publicationStmt>
   <sourceDesc><p>{escape(str(SOURCE))}, from the Repertorium Germanicum</p></sourceDesc>
  </fileDesc>
  <encodingDesc>
   <editorialDecl>
    <normalization>
     <p>Every abbreviation the workflow resolved is given as a
      &lt;choice&gt;: &lt;abbr&gt; is the reading of the RG, &lt;expan&gt; the
      expansion. Dropping the &lt;expan&gt; of every &lt;choice&gt; yields the
      text of the RG unchanged; dropping the &lt;abbr&gt; of every
      &lt;choice&gt; yields the expanded text. An &lt;abbr&gt; outside a
      &lt;choice&gt; is an abbreviation that was not resolved; it belongs to
      both readings.</p>
     <p>The @resp of an &lt;expan&gt; names the step that decided it.</p>
    </normalization>
   </editorialDecl>
  </encodingDesc>
  <profileDesc>
{statements}
  </profileDesc>
 </teiHeader>"""


# --------------------------------------------------------------------------
# building the document
# --------------------------------------------------------------------------

def stage_rows(path: Path) -> dict[tuple[int, int], list[dict]]:
    """The rows of a stage CSV per vita, in reading order, without empty ones."""
    table = pl.read_csv(path).sort(["volume", "nr_RG", "nr_suffix"])
    per_vita: dict[tuple[int, int], list[dict]] = {}
    for row in table.iter_rows(named=True):
        text = row["header_no_tags"] or row["regest_no_tags"]
        if text:
            per_vita.setdefault((row["volume"], row["nr_RG"]), []).append(row)
    return per_vita


def row_text(row: dict) -> str:
    return row["header_no_tags"] or row["regest_no_tags"] or ""


def build(source_texts: dict, stages: dict, anchors, known) -> tuple[str, dict]:
    """The whole document, plus the counts the report needs."""
    names = list(stages)
    final = names[-1]
    keys = sorted(set(source_texts) & set.intersection(*(set(stages[n]) for n in names)))

    info = {"vitae": 0, "regests": 0, "choices": 0, "kept": 0,
            "unplaced": 0, "refused": [], "skipped": []}
    volumes: dict[int, list[str]] = {}

    for key in keys:
        lines = source_texts[key].split("\n")
        rows = stages[final][key]
        if len(lines) != len(rows):
            # the source and the stage disagree about the regests: do not guess
            info["skipped"].append((key, f"{len(lines)} source lines, {len(rows)} rows"))
            continue

        body = []
        for index, (line, row) in enumerate(zip(lines, rows)):
            texts = {name: row_text(stages[name][key][index]) for name in names}
            if not texts[final]:
                continue
            segments, unplaced = mark_up(line, texts, anchors, known)
            markup = render(segments)
            abbreviated, expanded = readings(markup)
            if abbreviated != line:
                info["refused"].append((key, row["nr_suffix"], "source reading differs"))
                continue
            if expanded != texts[final]:
                info["refused"].append((key, row["nr_suffix"], "expanded reading differs"))
                continue

            info["choices"] += sum(1 for s in segments if s.expan is not None and not s.plain)
            info["kept"] += sum(1 for s in segments if s.kept)
            info["unplaced"] += unplaced
            info["regests"] += 1
            tag = "head" if row["nr_suffix"] == 0 else "p"
            body.append("    " + element(tag, markup, xml_id=f"rg-{row['id_RG_all']}"))

        if not body:
            continue
        info["vitae"] += 1
        volumes.setdefault(key[0], []).append(
            f'   <div type="vita" n="{key[1]}" xml:id="rg-{key[0]}-{key[1]}">\n'
            + "\n".join(body)
            + "\n   </div>"
        )

    divisions = "\n".join(
        f'  <div type="volume" n="{volume}">\n' + "\n".join(vitae) + "\n  </div>"
        for volume, vitae in sorted(volumes.items())
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<TEI xmlns="{TEI_NS}">\n'
        f"{header()}\n"
        " <text>\n  <body>\n"
        f"{divisions}\n"
        "  </body>\n </text>\n</TEI>\n"
    )
    return document, info


def render_report(info: dict, output: Path) -> str:
    lines = [
        "# TEI output",
        "",
        f"`{output}` -- both readings of the text in one document "
        "(`<abbr>` the RG, `<expan>` the expansion).",
        "",
        f"- {info['vitae']} vitae, {info['regests']} regests.",
        f"- {info['choices']} abbreviations expanded, as `<choice>`.",
        f"- {info['kept']} abbreviations the workflow left standing, as a bare `<abbr>`.",
        f"- {info['unplaced']} abbreviations whose expansion could not be located; "
        "they keep the reading of the RG.",
        "",
        "Every regest was round-tripped: dropping the `<expan>` elements "
        "reproduces the source text character for character, dropping the "
        "`<abbr>` elements reproduces the expanded text.",
    ]
    if info["refused"]:
        lines += ["", f"## Refused ({len(info['refused'])})", "",
                  "Regests whose markup did not round-trip. They are left out of "
                  "the document rather than written wrong.", ""]
        lines += [f"- {v}/{nr} suffix {suffix}: {why}"
                  for (v, nr), suffix, why in info["refused"]]
    if info["skipped"]:
        lines += ["", f"## Skipped ({len(info['skipped'])})", "",
                  "Vitae where the source and the stage output disagree about "
                  "the number of regests.", ""]
        lines += [f"- {v}/{nr}: {why}" for (v, nr), why in info["skipped"]]
    return "\n".join(lines) + "\n"


def to_tei(output: Path, write: bool) -> dict:
    source = pl.read_csv(SOURCE)
    source_texts = {(row["volume"], row["nr_RG"]): row["text"]
                    for row in source.iter_rows(named=True)}
    stages = {name: stage_rows(path) for name, _, path in STAGES if name != "source"}
    anchors = build_anchor_index(*GLOSSARY)
    known = known_abbreviations(*GLOSSARY)

    document, info = build(source_texts, stages, anchors, known)
    report = render_report(info, output)
    print(report)

    if write:
        output.parent.mkdir(parents=True, exist_ok=True)
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as file:
            file.write(document)
        with open(REPORT, "w", encoding="utf-8") as file:
            file.write(report)
        print(f"Wrote {output} ({len(document) / 1024:.0f} KB) and {REPORT}.")
    else:
        print(f"dry run -- pass --write to create {output}")
    return info


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write the expanded texts as a TEI document holding both readings."
    )
    parser.add_argument("--out", type=Path, default=OUTPUT,
                        help=f"the document to write (default: {OUTPUT})")
    parser.add_argument("--write", action="store_true",
                        help=f"write {OUTPUT} (default: dry run)")
    arguments = parser.parse_args()
    to_tei(arguments.out, arguments.write)


if __name__ == "__main__":
    main()
