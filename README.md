# AMSE thesis template

A thesis template for AMSE PhD students whose thesis is three or four working
papers. You keep writing each paper in its own Overleaf project; this template
assembles them into one manuscript without you rewriting anything by hand.

Built on Fabien Petit's AMSE template, which is itself derived from the official
Aix-Marseille University class.

## The five-minute version

```bash
# 1. put each paper in chapters/, one folder per chapter, in reading order
#    (Overleaf: Menu -> Download -> Source, then unzip)
chapters/01-first-paper/
chapters/02-second-paper/
chapters/03-third-paper/

# 2. import them
python3 tools/import_chapter.py

# 3. read the report the script prints, fix what it flags

# 4. compile
latexmk -pdf these.tex
```

On Overleaf: **Menu → Compiler → pdfLaTeX**, **Main document → `these.tex`**.
The bibliography uses **biber**, which Overleaf selects on its own.

## What the import script does for you

A working paper does not drop into a thesis unchanged. These are the things that
break, and the script handles all of them:

| Problem | What the script does |
| --- | --- |
| Two chapters both have a `\label{tab:main}` | prefixes every label and reference with `chap1-`, `chap2-`, … |
| `\input{tables/x}` no longer resolves from the thesis root | rewrites every `\input` path |
| `\includegraphics{figures/y}` likewise | sets `\graphicspath` per chapter, so your figure calls stay untouched |
| The paper's appendix uses `\section` | shifts its headings so the top one lands on `\subsection`, which the thesis numbers `1.A`, `1.B`, … `2.A` |
| The appendix's own `\input`ed sub-files | followed too — otherwise half the appendix keeps the level it had in the paper |
| The paper's macros live in its `main.tex` | copies `\newcommand`, `\definecolor`, `\newtheorem` into the thesis preamble as `\providecommand`, so two chapters cannot clash |
| An `abstract` field in a `.bib` containing a raw `%` | strips `abstract`, `keywords`, `doi`, `url`, `isbn` and escapes `%`, `&`, `#`, `_` (backup kept as `.bib.orig`) |
| Word smart quotes pasted into a `.tex` or `.bib` | replaces the Windows-1252 control bytes that make LaTeX stop |
| A blank line inside a `\caption{}` | replaces it with `\newline` (the argument is not `\long`, so a blank line aborts the run) |
| A `\caption` left outside any float | comments it out |
| A `\label` between `\begin{tabular}` and `\toprule` | moves it above the tabular (otherwise `Misplaced \noalign`) |
| A bare `\appendix` at the top of the paper's appendix | comments it out — otherwise every *later* chapter is renumbered into letters, silently |
| The `esttab` notes row left below `\end{tabular}` | rewrites it as a `\parbox` (otherwise `Misplaced \omit`) |
| A table fragment ending in one unmatched `}` | comments the brace out — it silently closed a group in the file above it |
| The same `\newsavebox` declared in five tables | guards each one, so it is allocated once and reused |
| A minus sign pasted as U+2212, or `≤`, `≈`, `→` | replaces them with the maths they mean |
| An empty `@misc{key}` left by Zotero | drops it — biber stops there and then builds no bibliography at all |
| Spaces in file names | renames the files and updates the references |

It also takes the **chapter title, the abstract, the keywords and the JEL codes**
straight out of the paper's own `main.tex`, so `tex/chapN.tex` arrives filled in.

## What it cannot do — read the report

The script never guesses. It prints a report and these are the lines to act on:

- **`[PACKAGE]`** — your paper loads a package this template does not provide.
  Add it to `tex/preamble-extra.tex` if the chapter needs it.
- **`[WARN] unclosed $`** — a math mode opened and never closed, usually a
  mangled table header from `esttab`. Only you know what the formula meant.
- **`[WARN] two subscripts in a row`** — `$X_i_t$` typesets as `X_i` and drops
  the rest. It is `X_{it}` you want, unless you really meant `X_{i_t}`.
- **`[WARN] \multicolumn with no tabular`** — the `\begin{tabular}` line of that
  table is gone. Nothing can guess the column spec back.
- **`[WARN] missing file`** — the paper `\input`s something that is not there.
- **`[TODO] no JEL codes`** — the paper never stated them; add them by hand.
- **`[WARN] starred appendix heading carrying its own number`** — you wrote
  `\subsection*{A.1 Additional Figures}` because nothing was numbering it. The
  thesis numbers it now, so drop the star and the `A.1`.
- **`[CHECK] no appendix detected`** — your appendix file is not named like one.
- **`[NOTE]`** — things it decided for you, worth a glance.

Three packages are worth knowing about before you start:

- **`amsthm` must not be loaded.** The class defines its own `proof`
  environment and the two collide. The script converts `\newtheorem*` into a
  plain unnumbered environment for you.
- **`sectsty` and `titlesec`** style sections. Drop them: in a thesis the
  chapter and section design belongs to the thesis, not to each paper.
- **`natbib`** is not needed. The class loads biblatex with `natbib=true`, so
  `\citet` and `\citep` work exactly as they did in your paper.

## Typography

The original AMSE template set the body in Adobe Utopia and every heading in
Helvetica. This one ships with Palatino throughout, because most economics
working papers are written in it and a chapter then looks the same inside the
thesis as it did on its own.

Neither is a requirement. Both are switches at the top of `amse_these.cls`:

```latex
\newif\ifpalatino      \palatinotrue       % \palatinofalse      -> Adobe Utopia
\newif\ifserifheadings \serifheadingstrue  % \serifheadingsfalse -> Helvetica headings
```

The title page is unaffected either way: it selects Titillium explicitly.

Everything else this template changes in the class is a fix rather than taste:
`tocloft` was loaded and never used (a long KOMA warning on every run), PDF
compression was off (a 250 MB thesis), `threeparttable` needs
`[para,online,flushleft]` for the `tablenotes` that econ papers put under
figures, and the cover uses the 2025 amU logo and the official AMU blue.

## Layout

| Path | What it is |
| --- | --- |
| `these.tex` | the main file. Two `\input` lines are generated; the rest is yours |
| `amse_these.cls` | the class: layout, fonts, bibliography, table and maths packages |
| `tex/preamble-extra.tex` | **your** packages and macros. Never overwritten |
| `tex/titre.tex` | title page — NNT/NL, defence date, jury |
| `tex/licence.tex` | affidavit — supervisors, date, signature |
| `tex/publi.tex` | publications, conferences, summer schools |
| `tex/resume.tex`, `tex/abstract.tex` | the FR and EN abstracts of the thesis |
| `tex/remercie.tex` | acknowledgements |
| `tex/intro.tex`, `tex/conc.tex` | general introduction and conclusion |
| `tex/chapN.tex` | one wrapper per chapter — generated once, then yours |
| `tex/_generated_*.tex` | rewritten on every import. Do not edit |
| `biblio.bib` | references for the general introduction and conclusion only |
| `chapters/` | your Overleaf exports |
| `logo/`, `fonts/`, `t1tit.fd` | title-page assets |
| `tools/` | the import script, its repair passes, and the caption splitter |

Each chapter keeps its own `.bib` and prints its own reference list. The general
introduction and conclusion each have one too, drawn from `biblio.bib`.

## How the appendices are numbered

Appendices come out as **1.A, 1.B, … 2.A, 2.B**, one letter per top-level
appendix heading, restarting at A in every chapter. Three things make that work,
all of them already in the generated `tex/chapN.tex`:

```latex
\clearpage
\addsec{Appendices}
\setcounter{subsection}{0}
\renewcommand{\thesubsection}{\thechapter.\Alph{subsection}}
```

The appendix's headings are `\subsection`, then `\subsubsection`, then
`\paragraph` — the import script shifts whatever the paper used until the top
one lands on `\subsection`. **Do not put a `\section` inside the appendix**: a
numbered `\section` resets the subsection counter, and the letters start again
from A halfway through. `\setcounter{subsection}{0}` is there because `\addsec`
is starred and does not reset it, so without it the first appendix would carry
on from the last section of the chapter body — 1.E, 1.F rather than 1.A, 1.B.

## Rerunning the import

Safe at any time. `tex/chapN.tex` belongs to you once it exists and the script
will not touch it again unless you pass `--force`. Every pass is idempotent, so
nothing gets prefixed twice. The repairs run once, on the first import; the
checks run every time, so you can fix what a `[WARN]` points at and run the
script again to see whether anything is left. The paper's untouched files are
kept in `chapters/<your-chapter>/_orig-overleaf/`.

```bash
python3 tools/import_chapter.py                    # all chapters
python3 tools/import_chapter.py chapters/02-care   # just one
python3 tools/import_chapter.py --force            # rewrite tex/chapN.tex too
```

## Captions that swallow the note

A working paper often keeps the whole note inside the caption:

```latex
\caption{\footnotesize \textbf{Effects of temperature on paid work.} This
figure presents the marginal effects from OLS estimates of equation (1) ...}
```

On its own that reads fine. In a thesis the List of Figures prints captions in
full, so twenty figures become twenty paragraphs. A second script moves the
prose under the figure and leaves the title in the caption:

```bash
python3 tools/split_caption_notes.py chapters/01-first-paper --dry-run
python3 tools/split_caption_notes.py chapters/01-first-paper
python3 tools/split_caption_notes.py chapters/01-first-paper --tables
```

It is deliberately **not** part of `import_chapter.py`: restructuring a float
the author wrote on purpose is a decision, not a repair. It only touches a
caption shaped *bold title, then a paragraph of prose* — a caption that is just
a title, or has no `\textbf`, is left alone and counted, and panel captions
inside `subfigure` or `minipage` are never touched. It keeps a `.precaption`
copy of every file it changes. Read the diff.

## Before you hand it in

- `tex/titre.tex`: NNT and numéro local from <https://depot-theses.univ-amu.fr/>,
  the defence date, and each jury member's role and institution.
- `tex/licence.tex`: your supervisors, the date, and your signature as
  `logo/signature.png`.
- The Creative Commons badge is `logo/by-nc-nd-eu.pdf`. If you want a different
  licence, swap the badge and the sentence under it.
- `\includegraphics` does not read `.eps` under pdfLaTeX. Convert to PDF:
  `gs -q -dNOPAUSE -dBATCH -dEPSCrop -sDEVICE=pdfwrite -sOutputFile=out.pdf in.eps`

## If Overleaf times out

Most of a compile of this size is spent reading figures, not typesetting. A
thesis whose figures are exported at 3000–6000 px wide can take five minutes;
the same thesis with those figures at 300 dpi takes about one.

The text is ~15.7 cm wide (A4, `DIV=12`), so at 300 dpi a full-width figure
needs 1860 px. Anything wider is weight for nothing:

```bash
# needs ImageMagick; keeps the aspect ratio, only shrinks what is too big
find chapters -iname '*.png' -exec mogrify -resize '1860x1860>' -strip {} +
```

Failing that, comment out the chapters you are not working on in
`tex/_generated_chapters.tex` — page numbers and cross-references will be
provisional until you compile the whole thing again.

## Credits and licensing

Adapted from the AMSE template by Fabien Petit, itself adapted from
[latexamu](https://github.com/SCD-Aix-Marseille-Universite/latexamu) by the
Aix-Marseille University library service.

`amse_these.cls`, the title page, the fonts and the logos come from that
template and remain its authors' work. What is new here is the import
toolchain in `tools/`, the chapter wrappers, and a handful of fixes to the
class listed under **Typography** above.

No licence is declared yet, on either side: Petit's template carries none, and
this repository is private for now. Before making it public, ask him — his
README calls the template a public good and invites changes, so it is a
formality, but it should be his call and not ours.

Please pass on your own fixes. The next cohort will thank you.
