# TEI output

`data/rg_expanded.xml` -- both readings of the text in one document (`<abbr>` the RG, `<expan>` the expansion).

- 156 vitae, 528 regests.
- 5168 abbreviations expanded, as `<choice>`.
- 17 abbreviations the workflow left standing, as a bare `<abbr>`.
- 0 abbreviations whose expansion could not be located; they keep the reading of the RG.

Every regest was round-tripped: dropping the `<expan>` elements reproduces the source text character for character, dropping the `<abbr>` elements reproduces the expanded text.
