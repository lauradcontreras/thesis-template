#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
split_caption_notes — move the explanatory prose out of \caption{} and under
the figure, so the List of Figures stays readable.

A working paper often carries the whole note inside the caption:

    \caption{\footnotesize \textbf{Effects of temperature on paid work.} This
    figure presents the marginal effects from OLS estimates of equation (1) ...
    Standard errors are clustered at the city level.}
    \label{fig:main}

On its own that is fine. In a thesis the List of Figures prints the caption in
full, so twenty figures produce twenty paragraphs where there should be twenty
lines. This rewrites the float to:

    \caption{Effects of temperature on paid work}
    \label{fig:main}

    \begin{minipage}{0.90\textwidth}
    \footnotesize
    \textit{Notes:} This figure presents the marginal effects from OLS
    estimates of equation (1) ... clustered at the city level.
    \end{minipage}

This is NOT part of import_chapter.py. It restructures floats the author wrote
deliberately, which is a decision, not a repair — so you run it when you want
it, on the chapters you want it on, and read the diff afterwards.

    python3 tools/split_caption_notes.py chapters/01-first-paper
    python3 tools/split_caption_notes.py chapters/01-first-paper --dry-run
    python3 tools/split_caption_notes.py chapters/01-first-paper --tables

It only touches a caption shaped "<title in \textbf{}> <a paragraph of prose>",
because that is the shape where the title and the note are unambiguous. A
caption that is only a title is left alone; so is one with no \textbf, and so
is a caption inside a subfigure. Everything it skips, it counts.

A copy of each file it changes is kept next to it as `<name>.tex.precaption`,
once, the first time.
"""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import texclean as tc                                        # noqa: E402

FLOAT_OPEN = re.compile(r"\\begin\{(figure|figure\*|sidewaysfigure|"
                        r"table|table\*|sidewaystable)\}")
SUBFLOAT = ("subfigure", "subfloat", "subtable", "minipage", "wrapfigure")

#: a caption body that opens with size switches and then a bold title
TITLED = re.compile(
    r"\A\s*(?:\\(?:footnotesize|small|scriptsize|tiny|normalsize|"
    r"large|Large|centering|singlespacing|justify)\s*)*"
    r"\\textbf\s*\{", re.S)

MINIPAGE = ("\\begin{minipage}{0.90\\textwidth}\n"
            "\\footnotesize\n"
            "\\textit{Notes:} %s\n"
            "\\end{minipage}\n")


def _commented(s, pos):
    r"""True if pos sits after an unescaped % on its own line.

    Papers are full of floats their author commented out rather than deleted.
    Rewriting inside one produces live LaTeX in a dead block, which is worse
    than leaving it: the notes appear on the page with no figure above them.
    """
    line_start = s.rfind("\n", 0, pos) + 1
    line = s[line_start:pos]
    return re.search(r"(?<!\\)%", line) is not None


def _float_blocks(s):
    """Yield (env, body_start, body_end) for each top-level float."""
    for m in FLOAT_OPEN.finditer(s):
        if _commented(s, m.start()):
            continue
        env = m.group(1)
        close = "\\end{%s}" % env
        end = s.find(close, m.end())
        if end == -1:
            continue
        yield env, m.end(), end


def _split_caption(body):
    r"""(title, notes) from a caption body, or None if it is not the shape."""
    if not TITLED.match(body):
        return None
    ob = body.index("{", body.index("\\textbf"))
    cb = tc._match_brace(body, ob)
    if cb == -1:
        return None
    title = body[ob + 1:cb].strip().rstrip(".").strip()
    notes = body[cb + 1:].strip()
    #: a bold lead-in with nothing after it is a title, not a title + note
    if not title or len(notes) < 80:
        return None
    return title, notes


def process(path, tables=False, dry_run=False):
    """Returns (rewritten, skipped_no_title, skipped_short)."""
    s = orig = open(path, encoding="utf-8", errors="replace").read()
    rewritten = no_title = short = 0
    #: right to left, so the offsets of earlier floats stay valid
    for env, start, end in reversed(list(_float_blocks(s))):
        if env.startswith("table") or env.startswith("sideways") and "table" in env:
            if not tables:
                continue
        block = s[start:end]
        #: the float's own caption is the first one that is not a panel's.
        #: Papers put panels in subfigure/minipage and give each its own
        #: \caption; those are (a) and (b) and must stay as they are.
        m = None
        for cand in re.finditer(r"\\caption(?!\*)\s*(\[[^\]]*\])?\s*\{", block):
            if _commented(block, cand.start()):
                continue
            head = block[:cand.start()]
            depth = sum(head.count("\\begin{%s}" % sub) - head.count("\\end{%s}" % sub)
                        for sub in SUBFLOAT)
            if depth <= 0:
                m = cand
                break
        if not m:
            continue
        if m.group(1):                       # already has a short LoF entry
            continue
        ob = block.index("{", m.end() - 1)
        cb = tc._match_brace(block, ob)
        if cb == -1:
            continue
        parts = _split_caption(block[ob + 1:cb])
        if parts is None:
            body = block[ob + 1:cb]
            if "\\textbf" not in body:
                no_title += 1
            else:
                short += 1
            continue
        title, notes = parts
        indent = re.match(r"[ \t]*", block[block.rfind("\n", 0, m.start()) + 1:]).group(0)
        new_block = (block[:m.start()] + "\\caption{%s}" % title
                     + block[cb + 1:].rstrip()
                     + "\n\n" + indent
                     + (MINIPAGE % notes).replace("\n", "\n" + indent).rstrip()
                     + "\n")
        s = s[:start] + new_block + s[end:]
        rewritten += 1
    if rewritten and not dry_run and s != orig:
        keep = path + ".precaption"
        if not os.path.exists(keep):
            shutil.copy2(path, keep)
        open(path, "w", encoding="utf-8").write(s)
    return rewritten, no_title, short


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__)
        sys.exit(1)
    tables = "--tables" in flags
    dry = "--dry-run" in flags
    total = notitle = shorts = 0
    for base in args:
        for path in tc.tex_files(base):
            r, nt, sh = process(path, tables=tables, dry_run=dry)
            total += r
            notitle += nt
            shorts += sh
            if r:
                print("%4d  %s" % (r, path))
    print()
    print("%d caption(s) %s" % (total, "would be split" if dry else "split"))
    if notitle:
        print("%d left alone: no \\textbf title to separate the note from"
              % notitle)
    if shorts:
        print("%d left alone: nothing after the title long enough to be a note"
              % shorts)
    if not tables:
        print("tables were not touched — pass --tables if you want them too")


if __name__ == "__main__":
    main()
