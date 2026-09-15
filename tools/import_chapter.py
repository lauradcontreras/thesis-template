#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_chapter — turn a standalone Overleaf paper into a thesis chapter.

    python3 tools/import_chapter.py                 # import every chapter folder
    python3 tools/import_chapter.py chapters/01-fez # just that one
    python3 tools/import_chapter.py --force         # also rewrite tex/chapN.tex

How to use it
-------------
1. Download your paper from Overleaf (Menu -> Download -> Source) and unzip it
   into `chapters/`, one folder per chapter. Name the folders so that they sort
   in the order you want the chapters to appear: 01-..., 02-..., 03-...
2. Run this script.
3. Read the report it prints, then compile.

What it does
------------
* reads the paper's own main .tex file and takes from it the chapter title, the
  abstract, the keywords and JEL codes, the order of the \\input commands, and
  which .bib files it uses;
* writes `tex/chapN.tex`, the wrapper the thesis compiles;
* prefixes every \\label and \\ref with `chapN-` so that two chapters can use
  the same label names, and rewrites every \\input path;
* sets \\graphicspath so that the paper's \\includegraphics keep working
  untouched;
* demotes the headings of the appendix files by one level so they sit under the
  thesis's "Appendices" section;
* cleans the .bib files and repairs the caption/label defects that stop a
  working paper from compiling inside a larger document;
* regenerates `tex/_generated_chapters.tex` and `tex/_generated_preamble.tex`.

What it cannot do
-----------------
It reports these instead of guessing:

* packages your paper's preamble loaded that this template does not provide;
* JEL codes, when the paper does not state them;
* which files are appendices, when they are not named like appendices.

`tex/chapN.tex` is yours once it exists: the script will not overwrite it unless
you pass --force. Everything else it writes is regenerated on every run.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import texclean as tc                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAPTERS_DIR = "chapters"

APPENDIX_HINTS = ("appendix", "appendices", "annexe", "annex", "supplementary")

SEEN_CMDS, SEEN_ENVS, SEEN_COLORS = set(), set(), {}

#: packages a paper often loads that this template deliberately handles itself.
HANDLED = {
    "geometry": "the class sets the page layout",
    "inputenc": "loaded by the class",
    "fontenc": "loaded by the class",
    "babel": "not used: the thesis body is in English",
    "natbib": "biblatex is loaded with natbib=true, so \\citet/\\citep work",
    "biblatex": "loaded by the class",
    "bibtex": "the thesis uses biber",
    "hyperref": "loaded by the class (must stay last)",
    "setspace": "loaded by the class",
    "microtype": "loaded by the class",
    "graphicx": "loaded by the class",
    "amsmath": "loaded by the class",
    "amssymb": "loaded by the class",
    "amsfonts": "loaded by the class",
    "booktabs": "loaded by the class",
    "multirow": "loaded by the class",
    "makecell": "loaded by the class",
    "array": "loaded by the class",
    "tabularx": "loaded by the class",
    "caption": "loaded by the class",
    "subcaption": "loaded by the class",
    "float": "loaded by the class",
    "tikz": "loaded by the class",
    "xcolor": "loaded by the class",
    "longtable": "loaded by the class",
    "rotating": "loaded by the class",
    "ragged2e": "loaded by the class",
    "threeparttable": "loaded by the class with [para,online,flushleft]",
    "adjustbox": "loaded by the class",
    "lipsum": "placeholder text, not needed in a finished thesis",
    "amsthm": "DO NOT load it: it clashes with the class's own `proof`",
    "sectsty": "drop it: chapter/section styling is the thesis's job",
    "titlesec": "drop it: chapter/section styling is the thesis's job",
    "fancyhdr": "drop it: KOMA-Script handles the headers",
    "subfig": "use subcaption (loaded by the class) instead",
    "subfigure": "obsolete and clashes with subcaption, which the class loads",
    "color": "superseded by xcolor, which the class loads",
    "parskip": "drop it: paragraph spacing is the thesis's call, not the paper's",
    "appendix": "not needed: the thesis opens its own Appendices section",
    "footmisc": "usually only there for the title block, which is not imported",
    "eurosym": "not needed: preamble-extra.tex defines \\euro",
}


# ---------------------------------------------------------------------------
# parsing the paper's main file
# ---------------------------------------------------------------------------

def strip_comments(s):
    """Remove LaTeX comments but keep \\%."""
    out = []
    for line in s.split("\n"):
        k, esc = None, False
        for i, ch in enumerate(line):
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
            elif ch == "%":
                k = i
                break
        out.append(line if k is None else line[:k])
    return "\n".join(out)


def find_main_file(chapter_dir):
    """The paper's standalone main file: \\documentclass + \\begin{document}."""
    best, best_score = None, -1
    for name in sorted(os.listdir(chapter_dir)):
        if not name.endswith(".tex"):
            continue
        path = os.path.join(chapter_dir, name)
        if not os.path.isfile(path):
            continue
        raw = open(path, encoding="utf-8", errors="replace").read()
        if "\\documentclass" not in raw or "\\begin{document}" not in raw:
            continue
        if "beamer" in raw.split("\\begin{document}")[0]:
            continue                                   # slides, not the paper
        body = strip_comments(raw).split("\\begin{document}", 1)[1]
        score = len(re.findall(r"\\input\{", body))
        if "main" in name.lower():
            score += 100
        if score > best_score:
            best, best_score = path, score
    return best


def brace_arg(s, start):
    """Return the balanced {...} argument that starts at `start`."""
    i = s.index("{", start)
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j
        j += 1
    return "", start


def tidy_text(s):
    """Flatten a LaTeX fragment into a single readable line."""
    s = re.sub(r"\\thanks\{", "\\\\thanks{", s)
    # drop \thanks{...} and other footnote-ish material
    while "\\thanks{" in s:
        k = s.index("\\thanks{")
        _, end = brace_arg(s, k)
        s = s[:k] + s[end + 1:]
    # size/spacing switches take no argument — never swallow the group after them
    for cmd in ("Large", "large", "LARGE", "Huge", "huge", "normalsize",
                "small", "footnotesize", "bigskip", "medskip", "smallskip",
                "noindent", "centering", "itshape", "bfseries"):
        s = re.sub(r"\\" + cmd + r"\b", "", s)
    # these do take one argument, and we want it gone with them
    for cmd in ("setstretch", "vspace", "hspace", "label"):
        s = re.sub(r"\\" + cmd + r"\*?\s*\{[^{}]*\}", "", s)
    # \textbf{...} around a title is styling from the paper's title block;
    # keep the words, drop the wrapper
    for _ in range(3):
        m = re.search(r"\\(?:textbf|textrm|textnormal)\s*\{", s)
        if not m:
            break
        inner, end = brace_arg(s, m.start())
        s = s[:m.start()] + inner + s[end + 1:]
    s = s.replace("\\\\", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip().strip("{}").strip()


def parse_main(path):
    """Pull title, abstract, keywords, JEL, inputs, bib files and packages."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    src = strip_comments(raw)
    preamble, _, body = src.partition("\\begin{document}")
    info = {"title": "", "abstract": "", "keywords": "", "jel": "",
            "inputs": [], "bibs": [], "packages": [], "frontmatter": [],
            "after_bib": [], "preamble": preamble}

    # Many papers keep \title / \maketitle / abstract in a separate file that
    # main.tex \inputs. Inline one level so we can find them there too.
    base = os.path.dirname(path)
    for m in re.finditer(r"\\(?:input|include)\{([^{}]*)\}", body):
        rel = m.group(1).strip()
        cand = os.path.join(base, rel if rel.endswith(".tex") else rel + ".tex")
        if not os.path.exists(cand):
            continue
        piece = strip_comments(open(cand, encoding="utf-8", errors="replace").read())
        if "\\maketitle" in piece or "\\begin{abstract}" in piece or "\\title{" in piece:
            info["frontmatter"].append(rel)
            src = src + "\n" + piece

    m = re.search(r"\\title\s*\{", src)
    if m:
        info["title"] = tidy_text(brace_arg(src, m.start())[0])

    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", src, re.S)
    if m:
        abstract = m.group(1)
        km = re.search(r"\\textbf\{\s*Keywords?[:\s]*\}?\s*:?\s*([^\\\n]*)", abstract)
        if km:
            info["keywords"] = km.group(1).strip().rstrip(".").strip()
        jm = re.search(r"(?:JEL[^:]*:|\\textbf\{\s*JEL[^}]*\}\s*:?)\s*([^\\\n]*)",
                       abstract)
        if jm:
            info["jel"] = jm.group(1).strip().rstrip(".").strip()
        abstract = re.split(r"\\vspace|\\textbf\{\s*Keywords?|\\textbf\{\s*JEL",
                            abstract)[0]
        info["abstract"] = tidy_text(abstract)

    for m in re.finditer(r"\\(?:input|include)\{([^{}]*)\}", body):
        p = m.group(1).strip()
        if p not in info["inputs"]:
            info["inputs"].append(p)

    #: everything the main file inputs after printing the bibliography is an
    #: appendix, whatever the file happens to be called
    tail = re.split(r"\\printbibliography|\\bibliography\{", body)
    if len(tail) > 1:
        for m in re.finditer(r"\\(?:input|include)\{([^{}]*)\}", tail[-1]):
            info["after_bib"].append(m.group(1).strip())

    for m in re.finditer(r"\\bibliography\{([^{}]*)\}", body):
        for b in m.group(1).split(","):
            b = b.strip()
            if b:
                info["bibs"].append(b if b.endswith(".bib") else b + ".bib")
    for m in re.finditer(r"\\addbibresource\{([^{}]*)\}", src):
        info["bibs"].append(m.group(1).strip())

    for m in re.finditer(r"\\(?:usepackage|RequirePackage)\s*(\[[^\]]*\])?\s*\{([^{}]*)\}",
                         preamble):
        for pkg in m.group(2).split(","):
            pkg = pkg.strip()
            if pkg and pkg not in info["packages"]:
                info["packages"].append(pkg)
    return info


def provided_definitions():
    """Commands and theorem environments the template already defines."""
    cmds, envs = set(), set()
    for rel in ("amse_these.cls", "tex/preamble-extra.tex"):
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        src = strip_comments(open(path, encoding="utf-8", errors="replace").read())
        for m in re.finditer(r"\\(?:new|renew|provide)command\*?\s*\{?\\([A-Za-z@]+)", src):
            cmds.add(m.group(1))
        for m in re.finditer(r"\\DeclareMathOperator\*?\s*\{?\\([A-Za-z@]+)", src):
            cmds.add(m.group(1))
        for m in re.finditer(r"\\newtheorem\*?\s*\{([^{}]*)\}", src):
            envs.add(m.group(1))
        for m in re.finditer(r"\\newenvironment\s*\{([^{}]*)\}", src):
            envs.add(m.group(1))
    envs.update({"proof", "abstract", "figure", "table"})
    return cmds, envs


def provided_packages():
    """Everything the class and preamble-extra.tex already load."""
    got = set()
    for rel in ("amse_these.cls", "tex/preamble-extra.tex"):
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        src = strip_comments(open(path, encoding="utf-8", errors="replace").read())
        for m in re.finditer(
                r"\\(?:usepackage|RequirePackage)\s*(\[[^\]]*\])?\s*\{([^{}]*)\}", src):
            for pkg in m.group(2).split(","):
                got.add(pkg.strip())
    return got


# ---------------------------------------------------------------------------
# writing the chapter wrapper
# ---------------------------------------------------------------------------

def is_appendix(path, after_bib=()):
    """An appendix either looks like one, or sits after the bibliography.

    Papers often call their appendix files A1, A2, annex... — names no list of
    hints will catch. But whatever they are called, they come after
    \\printbibliography in the paper's main file, and that is decisive.
    """
    low = path.lower()
    if any(h in low for h in APPENDIX_HINTS):
        return True
    return path in after_bib


def wrapper_text(prefix, folder, info, body_inputs, appendix_inputs):
    L = []
    A = L.append
    A("%% " + info["title"])
    A("%% Generated by tools/import_chapter.py from " + folder)
    A("%% This file is yours to edit: the script will not touch it again")
    A("%% unless you run it with --force.")
    A("")
    A("\\noindent \\textbf{Abstract}: " + (info["abstract"] or "% TODO"))
    A("\\\\")
    A("\\vspace{1em}\\\\")
    A("\\noindent\\textbf{Keywords:} " + (info["keywords"] or "% TODO"))
    A("\\\\")
    A("\\noindent\\textbf{JEL Codes:} " + (info["jel"] or "% TODO — not stated in the paper"))
    A("")
    A("\\clearpage")
    A("\\chaptertoc{}")
    A("")
    A("\\pagebreak")
    A("")
    A("%% The paper's \\includegraphics keep their original relative paths;")
    A("%% only the root changes.")
    A("\\graphicspath{{" + folder + "/}{./}}")
    A("")
    A("\\begin{refsection}")
    A("")
    A("    %%% CHAPTER BODY")
    A("    %% Each file carries its own \\section{...}.")
    for p in body_inputs:
        A("    \\input{%s/%s}" % (folder, p))
    A("")
    A("    %%% DO NOT CHANGE %%%")
    A("    \\printbibliography[heading=subbibintoc]")
    A("")
    A("    \\clearpage")
    A("    \\addsec{Appendices}")
    A("    %% The appendix numbers as 1.A, 1.B, ... 2.A, 2.B: its top-level")
    A("    %% headings are \\subsection, and \\thesubsection is the chapter")
    A("    %% number plus a letter. The counter has to be reset by hand —")
    A("    %% \\addsec is starred, so it does not reset it the way a numbered")
    A("    %% \\section would, and the appendix would carry on from wherever")
    A("    %% the last section of the chapter body left it (…1.E, 1.F).")
    A("    %% Do not put a \\section inside the appendix: it would reset the")
    A("    %% subsection counter and start the letters again from A.")
    A("    \\setcounter{subsection}{0}")
    A("    \\renewcommand{\\thesubsection}{\\thechapter.\\Alph{subsection}}")
    A("    %%% DO NOT CHANGE %%%")
    A("")
    if appendix_inputs:
        A("    %%% APPENDICES")
        A("    %% Headings shifted by the import script so the top level here")
        A("    %% is \\subsection; below it, \\subsubsection and \\paragraph.")
        for p in appendix_inputs:
            A("    \\input{%s/%s}" % (folder, p))
    else:
        A("    %% No appendix file was detected in this paper.")
        A("    %% \\input{%s/sections/appendix}" % folder)
    A("")
    A("\\end{refsection}")
    A("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def chapter_folders():
    base = os.path.join(ROOT, CHAPTERS_DIR)
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        p = os.path.join(base, name)
        if os.path.isdir(p) and not name.startswith("."):
            out.append(os.path.join(CHAPTERS_DIR, name))
    return out


def import_one(folder, index, force, report):
    abs_dir = os.path.join(ROOT, folder)
    state = tc.read_state(abs_dir)
    prefix = state.get("prefix") or ("chap%d-" % index)
    key = prefix.rstrip("-")

    main = find_main_file(abs_dir)
    if not main:
        report.append(("ERROR", folder,
                       "no standalone .tex with \\documentclass and "
                       "\\begin{document} found — is this an Overleaf export?"))
        return None
    info = parse_main(main)

    body_inputs, appendix_inputs = [], []
    for p in info["inputs"]:
        if p in info["frontmatter"]:
            report.append(("NOTE", folder,
                           "%s holds the paper's title block and abstract — not "
                           "included in the chapter; its abstract was reused above "
                           "the chapter body instead" % p))
            continue
        rel = p if p.endswith(".tex") else p + ".tex"
        target = os.path.join(abs_dir, rel)
        if " " in p:
            # a space in an \input path is fragile; rename the file once
            new_rel, new_p = rel.replace(" ", "_"), p.replace(" ", "_")
            if os.path.exists(target):
                os.rename(target, os.path.join(abs_dir, new_rel))
                report.append(("FIXED", folder,
                               "renamed '%s' -> '%s' (spaces in an \\input path "
                               "are fragile)" % (os.path.basename(rel),
                                                 os.path.basename(new_rel))))
            p, target = new_p, os.path.join(abs_dir, new_rel)
        if not os.path.exists(target):
            alt = target.replace(" ", "_")
            if alt != target and os.path.exists(alt):
                p = p.replace(" ", "_")
            else:
                report.append(("WARN", folder,
                               "the paper does \\input{%s} but that file is missing "
                               "— left in the wrapper, comment it out if unused" % p))
        (appendix_inputs if is_appendix(p, info["after_bib"])
         else body_inputs).append(p)

    # --- repair and namespace the paper's own files -------------------------
    #: An appendix file often does nothing but \input five more. The headings
    #: are in those five, so the set has to be followed to the end or half the
    #: appendix keeps the level it had in the paper.
    appendix_files, queue = set(), [p for p in appendix_inputs]
    while queue:
        p = queue.pop()
        rel = os.path.normpath(p if p.endswith(".tex") else p + ".tex")
        if rel in appendix_files:
            continue
        appendix_files.add(rel)
        target = os.path.join(abs_dir, rel)
        if not os.path.isfile(target):
            continue
        body = open(target, encoding="utf-8", errors="replace").read()
        for m in tc.INPUT_RE.finditer(body):
            child = m.group(2).strip()
            #: paths are still the paper's own at this point, but prefix_inputs
            #: may already have rewritten them to start with the chapter folder
            if child.startswith(folder + "/"):
                child = child[len(folder) + 1:]
            queue.append(child)
    #: Most projects keep their text in sections/ or similar, but some put
    #: every file at the top level. Those must be processed too — all except
    #: the standalone documents (main file, slides, comment sheets), which
    #: are the ones carrying \documentclass.
    targets = []
    for sub in sorted(os.listdir(abs_dir)):
        sub_dir = os.path.join(abs_dir, sub)
        if os.path.isdir(sub_dir) and sub != "_orig-overleaf":
            targets.extend(tc.tex_files(sub_dir))
        elif sub.endswith(".tex") and os.path.isfile(sub_dir):
            head = open(sub_dir, encoding="utf-8", errors="replace").read(4000)
            if "\\documentclass" not in head:
                targets.append(sub_dir)

    if not state.get("namespaced"):
        backup = os.path.join(abs_dir, "_orig-overleaf")
        if not os.path.isdir(backup):
            os.makedirs(backup)
            import shutil
            for sub in sorted(os.listdir(abs_dir)):
                src = os.path.join(abs_dir, sub)
                if os.path.isdir(src) and sub != "_orig-overleaf":
                    shutil.copytree(src, os.path.join(backup, sub),
                                    ignore=shutil.ignore_patterns(
                                        "*.png", "*.pdf", "*.jpg", "*.jpeg",
                                        ".DS_Store"))
                elif sub.endswith(".tex") and os.path.isfile(src):
                    #: flat projects keep everything at the top level, and those
                    #: files get rewritten too, so they need the backup as well
                    shutil.copy2(src, os.path.join(backup, sub))

        uni = caps = multicols = braces = allocs = appendices = 0
        for path in targets:
            uni += tc.fix_unicode(path)
            b, o, l, n, mc = tc.fix_captions(path)
            caps += b + o + l + n
            multicols += mc
            braces += 1 if tc.fix_stray_brace(path) else 0
            rel = os.path.relpath(path, abs_dir).replace(os.sep, "/")
            s = orig = open(path, encoding="utf-8", errors="replace").read()
            s, a = tc.guard_allocations(s)
            allocs += a
            s, ap = tc.neutralise_appendix(s)
            appendices += ap
            s = tc.prefix_refs(s, prefix)
            s = tc.prefix_inputs(s, folder)
            if s != orig:
                open(path, "w", encoding="utf-8").write(s)

        #: The appendix's top heading has to come out as \subsection, because
        #: that is the level tex/chapN.tex numbers 1.A, 1.B, 2.A. Papers open
        #: their appendix at whatever level suited the paper, so the shift is
        #: worked out from the shallowest heading across the whole appendix and
        #: applied to all of it at once — never file by file, or two files that
        #: started at different levels would end up at the same one.
        appendix_paths = [os.path.join(abs_dir, r) for r in sorted(appendix_files)
                          if os.path.isfile(os.path.join(abs_dir, r))]
        used = set()
        for path in appendix_paths:
            used |= tc.heading_levels(open(path, encoding="utf-8",
                                           errors="replace").read())
        if used:
            shift = tc.APPENDIX_TOP - min(used)
            moved = 0
            for path in appendix_paths:
                s = open(path, encoding="utf-8", errors="replace").read()
                s, n = tc.shift_headings(s, shift)
                moved += n
                if n:
                    open(path, "w", encoding="utf-8").write(s)
            if moved:
                report.append(("FIXED", folder,
                               "%d appendix heading(s) moved %s %d level(s), so the "
                               "appendix starts at \\subsection and numbers as "
                               "%s.A, %s.B, ..."
                               % (moved, "down" if shift > 0 else "up", abs(shift),
                                  prefix[4:-1], prefix[4:-1])))
        if uni:
            report.append(("FIXED", folder,
                           "%d Windows-1252 control characters and Unicode "
                           "maths symbols" % uni))
        if caps:
            report.append(("FIXED", folder, "%d caption/label defects" % caps))
        if multicols:
            report.append(("FIXED", folder,
                           "%d \\multicolumn row(s) sitting outside any tabular "
                           "— rewritten as \\parbox" % multicols))
        if braces:
            report.append(("FIXED", folder,
                           "%d file(s) ended with one unmatched } — commented out"
                           % braces))
        if appendices:
            report.append(("FIXED", folder,
                           "%d bare \\appendix removed — it would have renumbered "
                           "every chapter after this one into letters" % appendices))
        if allocs:
            report.append(("NOTE", folder,
                           "%d \\newsavebox/\\newlength/\\newcounter guarded, so "
                           "a declaration repeated across tables is made once"
                           % allocs))
        imgs = tc.fix_spaced_graphics(abs_dir)
        if imgs:
            report.append(("FIXED", folder,
                           "%d image file(s) had spaces in the name — renamed and "
                           "references updated" % imgs))

    #: These only look; they never write. They run on every import, not just
    #: the first, because the workflow is "run it, fix what it flags, run it
    #: again" and a second run that says nothing would look like all clear.
    CHECKS = (
        (tc.check_math_delimiters,
         "unclosed $ on line(s) %s — fix by hand, only you know what the "
         "formula should say"),
        (tc.check_orphan_multicolumn,
         "\\multicolumn with no tabular around it on line(s) %s — the "
         "\\begin{tabular} line looks lost; LaTeX stops here"),
        (tc.check_double_subscripts,
         "two subscripts in a row on line(s) %s — `X_i_t` typesets as `X_i` "
         "and drops the rest; write `X_{it}` if that is what you meant"),
    )
    for path in targets:
        rel = os.path.relpath(path, abs_dir).replace(os.sep, "/")
        for check, message in CHECKS:
            lines = check(path)
            if not lines:
                continue
            where = ", ".join(str(n) for n in lines[:6])
            if len(lines) > 6:
                where += ", ..."
            report.append(("WARN", folder, "%s: %s" % (rel, message % where)))

    for rel in sorted(appendix_files):
        path = os.path.join(abs_dir, rel)
        if not os.path.isfile(path):
            continue
        manual = tc.check_manual_appendix_labels(path)
        if manual:
            where = ", ".join(str(n) for n in manual[:6])
            if len(manual) > 6:
                where += ", ..."
            report.append(("WARN", folder,
                           "%s: starred appendix heading(s) carrying their own "
                           "number on line(s) %s — the thesis numbers them now, "
                           "so drop the star and the A.1 in the title, or they "
                           "will read \"1.A A.1 Additional Figures\"" % (rel, where)))

    case_fixed, missing = tc.fix_path_case(abs_dir, folder)
    if case_fixed:
        report.append(("FIXED", folder,
                       "%d path(s) did not match the file name's case — "
                       "harmless on macOS, fatal on Overleaf and Linux"
                       % case_fixed))
    for ref in missing[:8]:
        report.append(("WARN", folder,
                       "%s is used but no such file exists in the chapter" % ref))
    if len(missing) > 8:
        report.append(("WARN", folder,
                       "... and %d more missing files" % (len(missing) - 8)))

        state["namespaced"] = True

    # --- bibliography --------------------------------------------------------
    bibs = []
    for b in info["bibs"]:
        cand = os.path.join(abs_dir, b)
        if os.path.exists(cand):
            if not state.get("bib_cleaned"):
                bad = tc.fix_unicode(cand)
                if bad:
                    report.append(("FIXED", folder,
                                   "%s: %d Windows-1252 control characters" % (b, bad)))
                dropped, _, empty = tc.clean_bib(cand)
                if dropped:
                    report.append(("FIXED", folder,
                                   "%s: %d noisy fields dropped" % (b, dropped)))
                if empty:
                    report.append(("FIXED", folder,
                                   "%s: %d entry/entries had a citation key and "
                                   "nothing else — dropped, because biber stops "
                                   "on one and then no bibliography is built at "
                                   "all" % (b, empty)))
            bibs.append("%s/%s" % (folder, b))
        else:
            report.append(("WARN", folder,
                           "%s is referenced by the paper but missing" % b))
    state["bib_cleaned"] = True

    # --- the wrapper ---------------------------------------------------------
    wrapper_rel = "tex/%s.tex" % key
    wrapper = os.path.join(ROOT, wrapper_rel)
    if os.path.exists(wrapper) and not force:
        report.append(("KEPT", folder, "%s already exists, left untouched" % wrapper_rel))
    else:
        open(wrapper, "w", encoding="utf-8").write(
            wrapper_text(prefix, folder, info, body_inputs, appendix_inputs))
        report.append(("WROTE", folder, wrapper_rel))

    if not info["jel"]:
        report.append(("TODO", folder, "no JEL codes in the paper — add them to " + wrapper_rel))
    if not appendix_inputs:
        report.append(("CHECK", folder,
                       "no appendix file detected; if the paper has one, add it "
                       "to %s and rerun with --force" % wrapper_rel))

    # --- preamble gaps -------------------------------------------------------
    have = provided_packages()
    for pkg in info["packages"]:
        if pkg in have:
            continue
        if pkg in HANDLED:
            continue
        report.append(("PACKAGE", folder,
                       "%s — the paper loads it, the template does not. Add it to "
                       "tex/preamble-extra.tex if the chapter needs it." % pkg))
    for pkg in info["packages"]:
        if pkg in ("amsthm", "sectsty", "titlesec", "subfig", "fancyhdr"):
            report.append(("NOTE", folder, "%s: %s" % (pkg, HANDLED[pkg])))

    macros, clashes = tc.extract_macros(info["preamble"], SEEN_CMDS, SEEN_ENVS,
                                        SEEN_COLORS)
    for name in clashes:
        report.append(("NOTE", folder,
                       "colour '%s' is defined differently here than in an earlier "
                       "chapter — the earlier definition is the one in force" % name))
    if macros:
        report.append(("FIXED", folder,
                       "%d macro(s) defined in the paper's preamble carried over "
                       "into tex/_generated_preamble.tex" % len(macros)))

    state["prefix"] = prefix
    state["main"] = os.path.relpath(main, abs_dir)
    tc.write_state(abs_dir, state)
    return {"key": key, "folder": folder, "title": info["title"], "bibs": bibs,
            "macros": macros}


def write_generated(chapters):
    lines = ["%% GENERATED by tools/import_chapter.py — do not edit.",
             "%% Rerun the script instead.", ""]
    for c in chapters:
        title = c["title"] or "TITLE — not found in the paper's main file"
        lines.append("\t\\chapter{%s}\\label{%s}" % (title, c["key"]))
        lines.append("\t\\input{tex/%s}" % c["key"])
        lines.append("")
    open(os.path.join(ROOT, "tex/_generated_chapters.tex"), "w",
         encoding="utf-8").write("\n".join(lines))

    lines = ["%% GENERATED by tools/import_chapter.py — do not edit.", ""]
    lines.append("%% Bibliography files found in the chapters.")
    for c in chapters:
        for b in c["bibs"]:
            lines.append("\\addbibresource{%s}" % b)
    lines.append("")
    lines.append("\\makeatletter")
    lines.append("%% Macros the papers defined in their own preamble. \\newcommand")
    lines.append("%% became \\providecommand so two chapters cannot clash; if two")
    lines.append("%% papers define the same shorthand differently, the first one wins")
    lines.append("%% and you should rename one of them by hand.")
    for c in chapters:
        if c.get("macros"):
            lines.append("")
            lines.append("%% --- from " + c["folder"] + " ---")
            lines.extend(c["macros"])
    lines.append("")
    lines.append("\\makeatother")
    lines.append("")
    open(os.path.join(ROOT, "tex/_generated_preamble.tex"), "w",
         encoding="utf-8").write("\n".join(lines))


def main():
    global SEEN_CMDS, SEEN_ENVS
    SEEN_CMDS, SEEN_ENVS = provided_definitions()
    SEEN_COLORS.clear()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv

    folders = chapter_folders()
    if args:
        wanted = {os.path.normpath(a).replace(os.sep, "/").rstrip("/") for a in args}
        selected = [f for f in folders if f in wanted]
        if not selected:
            print("No chapter folder matched. Available: " + ", ".join(folders) or
                  "none — put your Overleaf exports in chapters/")
            sys.exit(1)
    else:
        selected = folders

    if not folders:
        print("Nothing to import: chapters/ is empty.")
        print("Unzip each Overleaf export into its own folder there, named so")
        print("that they sort in reading order (01-..., 02-..., 03-...).")
        sys.exit(1)

    report, chapters = [], []
    for i, folder in enumerate(folders, start=1):
        if folder in selected:
            c = import_one(folder, i, force, report)
        else:
            state = tc.read_state(os.path.join(ROOT, folder))
            key = (state.get("prefix") or "chap%d-" % i).rstrip("-")
            main_file = find_main_file(os.path.join(ROOT, folder))
            title = parse_main(main_file)["title"] if main_file else ""
            bibs = []
            if main_file:
                for b in parse_main(main_file)["bibs"]:
                    if os.path.exists(os.path.join(ROOT, folder, b)):
                        bibs.append("%s/%s" % (folder, b))
            macros = []
            if main_file:
                macros, _ = tc.extract_macros(parse_main(main_file)["preamble"],
                                              SEEN_CMDS, SEEN_ENVS, SEEN_COLORS)
            c = {"key": key, "folder": folder, "title": title, "bibs": bibs,
                 "macros": macros}
        if c:
            chapters.append(c)

    write_generated(chapters)

    print("")
    print("Chapters")
    print("--------")
    for c in chapters:
        print("  %-6s %-28s %s" % (c["key"], c["folder"], c["title"][:60] or "(no title)"))
    print("")
    order = {"ERROR": 0, "PACKAGE": 1, "WARN": 2, "TODO": 3, "CHECK": 4,
             "NOTE": 5, "FIXED": 6, "WROTE": 7, "KEPT": 8}
    report.sort(key=lambda r: order.get(r[0], 9))
    if report:
        print("Report")
        print("------")
        for kind, folder, msg in report:
            print("  [%-7s] %-22s %s" % (kind, os.path.basename(folder), msg))
    print("")
    print("Now compile:  latexmk -pdf these.tex")
    print("")


if __name__ == "__main__":
    main()
