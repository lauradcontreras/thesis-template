#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
texclean — the repair passes used when importing an Overleaf paper.

Used as a library by import_chapter.py. Can also be run on its own:

    python3 tools/texclean.py bib     chapters/01-fez/references.bib
    python3 tools/texclean.py unicode chapters/01-fez
    python3 tools/texclean.py caption chapters/01-fez

Every pass is idempotent: running it twice changes nothing the second time.
"""
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# 1. Bibliography
# ---------------------------------------------------------------------------

DROP_FIELDS = {"abstract", "keywords", "doi", "url", "urldate", "isbn", "issn",
               "eprint", "eprinttype", "eprintclass", "file", "annote",
               "language", "bdsk-url-1", "bdsk-url-2", "bdsk-url-3"}


def _split_fields(body):
    """Split an entry body into top-level `field = value` chunks."""
    out, buf, depth, inq = [], "", 0, False
    for ch in body:
        if ch == "{" and not inq:
            depth += 1
        elif ch == "}" and not inq:
            depth -= 1
        elif ch == '"' and depth == 0:
            inq = not inq
        if ch == "," and depth == 0 and not inq:
            out.append(buf)
            buf = ""
            continue
        buf += ch
    if buf.strip():
        out.append(buf)
    return out


def _escape_specials(s):
    s = re.sub(r"(?<!\\)%", r"\\%", s)
    s = re.sub(r"(?<!\\)&", r"\\&", s)
    s = re.sub(r"(?<!\\)#", r"\\#", s)
    #: an underscore outside math breaks the .bbl (e.g. number = {suppl_1}),
    #: but inside $...$ it is a subscript and must stay as it is
    parts = s.split("$")
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"(?<!\\)_", r"\\_", parts[i])
    return "$".join(parts)


#: `@misc{key}` with no fields at all — Zotero writes one whenever an item was
#: added by drag-and-drop and never filled in. biber stops on it with
#: "syntax error: found }, expected ," and no bibliography is produced at all.
BARE_KEY = re.compile(r"\s*[^\s=,{}\"]+\s*\Z")


def clean_bib(path):
    """Drop noisy fields and escape % & # . Returns (dropped, backup_path, empty)."""
    src = open(path, encoding="utf-8", errors="replace").read()
    backup = path + ".orig"
    if not os.path.exists(backup):
        open(backup, "w", encoding="utf-8").write(src)

    out, i, dropped, empty = [], 0, 0, 0
    while True:
        at = src.find("@", i)
        if at == -1:
            out.append(src[i:])
            break
        out.append(src[i:at])
        ob = src.find("{", at)
        if ob == -1:
            out.append(src[at:])
            break
        depth, j = 0, ob
        while j < len(src):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        entry, head = src[at:j + 1], src[at:ob + 1]
        parts = _split_fields(src[ob + 1:j])
        if not parts:
            out.append(entry)
            i = j + 1
            continue
        kept = [parts[0]]                        # citation key
        for part in parts[1:]:
            m = re.match(r"\s*([A-Za-z][A-Za-z0-9_-]*)\s*=", part)
            if m and m.group(1).lower() in DROP_FIELDS:
                dropped += 1
                continue
            kept.append(_escape_specials(part))
        if len(kept) == 1 and BARE_KEY.match(kept[0]):
            #: nothing but a citation key: not a reference, and fatal to biber
            empty += 1
            out.append("%% [empty entry dropped by the import script: @"
                       + head[1:].rstrip("{") + "{" + kept[0].strip() + "}]\n")
            i = j + 1
            continue
        out.append(head + ",".join(kept) + "\n}")
        i = j + 1

    open(path, "w", encoding="utf-8").write("".join(out))
    return dropped, backup, empty


# ---------------------------------------------------------------------------
# 2. Windows-1252 control characters
# ---------------------------------------------------------------------------

C1_REMAP = {0x91: "\u2018", 0x92: "\u2019", 0x93: "\u201c", 0x94: "\u201d",
            0x96: "--", 0x97: "---", 0x85: "\\dots ", 0x95: "\u2022",
            0xA0: " "}

#: Maths symbols that word processors, Stata logs and web pages emit as
#: Unicode and that T1 has no text-mode glyph for, so each one stops the run
#: with "Unicode character not set up for use with LaTeX". The replacement
#: depends on where the character sits: U+2212 is a minus sign, which is `-`
#: inside $...$ and `$-$` outside it.
#:
#: Only characters that actually fail belong here. ×, ÷, ±, ° and ′ all
#: typeset as they are and are left alone — a pass that rewrites working input
#: is a pass whose output the author has to proofread.
MATH_REMAP = {0x2212: "-", 0x2264: "\\leq", 0x2265: "\\geq",
              0x2248: "\\approx", 0x2260: "\\neq", 0x221E: "\\infty",
              0x2211: "\\sum", 0x220F: "\\prod", 0x221A: "\\sqrt{}",
              0x2192: "\\rightarrow", 0x21D2: "\\Rightarrow",
              0x2208: "\\in", 0x2211: "\\sum", 0x2202: "\\partial"}


def fix_unicode(path):
    """Replace stray Windows-1252 control bytes and Unicode maths. Returns how many."""
    s = open(path, encoding="utf-8", errors="replace").read()
    out, hits, math, esc = [], 0, False, False
    for ch in s:
        o = ord(ch)
        if esc:                                  # the char after a backslash
            esc = False
            out.append(ch)
            continue
        if ch == "\\":
            esc = True
            out.append(ch)
            continue
        if ch == "$":
            math = not math
            out.append(ch)
            continue
        if o in C1_REMAP:
            out.append(C1_REMAP[o])
            hits += 1
        elif o in MATH_REMAP:
            sym = MATH_REMAP[o]
            out.append(sym if math else "$" + sym + "$")
            hits += 1
        elif 0x80 <= o <= 0x9F:
            hits += 1                            # drop it
        else:
            out.append(ch)
    if hits:
        open(path, "w", encoding="utf-8").write("".join(out))
    return hits


# ---------------------------------------------------------------------------
# 3. Captions and labels
# ---------------------------------------------------------------------------

FLOATS = ("figure", "table", "sidewaystable", "sidewaysfigure", "longtable",
          "subfigure", "wrapfigure", "figure*", "table*")

LABEL_IN_TABULAR = re.compile(
    r"(?P<beg>\\begin\{(?:tabular|tabularx|tabular\*)\}[^\n]*\n)"
    r"(?P<lab>(?:[ \t]*\\label\{[^}]*\}[ \t]*\n)+)")

VERTICAL_NEWLINE = re.compile(r"\n[ \t]*\n[ \t]*\\newline[ \t]*\n")


def _match_brace(s, i):
    depth = 0
    while i < len(s):
        if s[i] == "{" and (i == 0 or s[i - 1] != "\\"):
            depth += 1
        elif s[i] == "}" and s[i - 1] != "\\":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _fix_blank_lines_in_captions(s):
    """A blank line inside \\caption{} ends the paragraph and breaks the run."""
    out, i, n = [], 0, 0
    for m in re.finditer(r"\\caption\*?\s*(\[[^\]]*\])?\s*\{", s):
        ob = s.index("{", m.end() - 1)
        cb = _match_brace(s, ob)
        if cb == -1:
            continue
        body = s[ob:cb]
        new = re.sub(r"\n[ \t]*\n", "\n\\\\newline\n", body)
        if new != body:
            out.append(s[i:ob])
            out.append(new)
            i = cb
            n += 1
    out.append(s[i:])
    return "".join(out), n


def _comment_orphan_captions(s):
    """A \\caption outside any float aborts the compilation."""
    depth, n, lines = 0, 0, s.split("\n")
    for k, line in enumerate(lines):
        for env in FLOATS:
            depth += line.count("\\begin{" + env + "}")
            depth -= line.count("\\end{" + env + "}")
        depth = max(depth, 0)
        st = line.lstrip()
        if depth == 0 and (st.startswith("\\caption{") or st.startswith("\\caption*{")):
            lines[k] = "%% [orphan caption commented out by the import script] " + line
            n += 1
    return "\n".join(lines), n


TABULARS = ("tabular", "tabularx", "tabular*", "longtable", "tabu", "array")

MULTICOL_RE = re.compile(r"\\multicolumn\s*\{")
PBOX_SPEC = re.compile(r"^\s*[pmb]\{(?P<w>[^{}]*)\}\s*$")


def _orphan_multicolumns(s):
    r"""Yield (start, end_of_last_group, colspec, body, closed_before) for every
    \multicolumn that is not inside a tabular at that point in the file."""
    for m in MULTICOL_RE.finditer(s):
        before = s[:m.start()]
        opened = sum(before.count("\\begin{" + e + "}") for e in TABULARS)
        closed = sum(before.count("\\end{" + e + "}") for e in TABULARS)
        if opened > closed:
            continue
        try:
            ob = s.index("{", m.end() - 1)       # {ncols}
            cb = _match_brace(s, ob)
            if cb == -1 or s[cb + 1:].lstrip()[:1] != "{":
                continue
            ob2 = s.index("{", cb + 1)           # {colspec}
            cb2 = _match_brace(s, ob2)
            if cb2 == -1 or s[cb2 + 1:].lstrip()[:1] != "{":
                continue
            ob3 = s.index("{", cb2 + 1)          # {body}
            cb3 = _match_brace(s, ob3)
        except ValueError:
            continue
        if cb3 == -1:
            continue
        yield m.start(), cb3 + 1, s[ob2 + 1:cb2], s[ob3 + 1:cb3], closed > 0


def _fix_orphan_multicolumn(s):
    r"""The table-notes row left below \end{tabular}: "Misplaced \omit".

    Stata's esttab writes the notes as one more \multicolumn row, spanning the
    table in a p{...} column. Authors move it out from under \end{tabular} so
    that \resizebox does not scale the notes with the numbers, and it then sits
    in ordinary text, where \multicolumn expands to \multispan -> \omit and
    stops the run. \parbox is the box the author meant.

    Deliberately narrow: only a paragraph column (p/m/b), and only after a
    tabular has been closed earlier in the file. A \multicolumn{1}{c}{(1)} with
    no tabular anywhere means the \begin{tabular} line itself was lost, and
    that is not something to guess at — check_orphan_multicolumn reports it.
    """
    out, i, n = [], 0, 0
    for start, end, spec, body, closed_before in _orphan_multicolumns(s):
        if start < i or not closed_before:
            continue
        w = PBOX_SPEC.match(spec)
        if not w:
            continue
        out.append(s[i:start])
        out.append("%% [table-notes \\multicolumn left outside the tabular, "
                   "rewritten as \\parbox by the import script]\n")
        out.append("\\parbox{%s}{%s}" % (w.group("w"), body))
        i = end
        #: its row terminator would now be a \\ in vertical mode
        while s[i:i + 1] in (" ", "\t"):
            i += 1
        if s[i:i + 2] == "\\\\":
            i += 2
        n += 1
    out.append(s[i:])
    return "".join(out), n


BARE_APPENDIX = re.compile(r"(?m)^([ \t]*)\\appendix[ \t]*$")


def neutralise_appendix(s):
    r"""A bare \appendix inside a chapter renumbers every chapter after it.

    In a standalone paper the appendix file opens with \appendix and that is
    correct. In a thesis it is a document-wide switch: from that line on
    \thechapter counts in letters, so the chapter *after* this one comes out
    as "Appendix A" in the text, the header and the table of contents. It is
    also silent — no warning, no error, just a thesis whose third chapter is
    called A. Each chapter's own appendix is set up by tex/chapN.tex instead.
    """
    return BARE_APPENDIX.subn(
        lambda m: m.group(1) + "%% [\\appendix removed by the import script: "
                  "it would renumber every chapter after this one; the "
                  "chapter's appendix is set up in tex/chapN.tex]", s)


def check_orphan_multicolumn(path):
    r"""Line numbers of a \multicolumn with no tabular open and none closed
    before it — almost always a lost \begin{tabular} line. Reported only."""
    s = open(path, encoding="utf-8", errors="replace").read()
    return sorted({s.count("\n", 0, start) + 1
                   for start, _, _, _, closed in _orphan_multicolumns(s)
                   if not closed})


def fix_captions(path):
    """Caption/label/table defects. Returns (blank_lines, orphans, labels, newlines, multicols)."""
    s = orig = open(path, encoding="utf-8", errors="replace").read()
    s, blanks = _fix_blank_lines_in_captions(s)
    s, orphans = _comment_orphan_captions(s)
    s, labels = LABEL_IN_TABULAR.subn(lambda m: m.group("lab") + m.group("beg"), s)
    s, newlines = VERTICAL_NEWLINE.subn(
        "\n\n%% [\\\\newline in vertical mode removed by the import script]\n", s)
    s, multicols = _fix_orphan_multicolumn(s)
    if s != orig:
        open(path, "w", encoding="utf-8").write(s)
    return blanks, orphans, labels, newlines, multicols


ALLOC_RE = re.compile(r"(?<![{\\])\\(newsavebox|newlength|newcounter)\s*\{\\?([A-Za-z@]+)\}")


def guard_allocations(s):
    r"""\newsavebox et al. declared twice: "Command \tempbox already defined".

    A paper that builds several tables the same way copies the whole block,
    \newsavebox included. On its own that is one \newsavebox per file and TeX
    never notices; in a thesis every file is read into one document and the
    second declaration is an error. Guarding each one keeps the first and makes
    the rest reuse it, whatever order the files end up being read in.
    """
    def sub(m):
        cmd, name = m.group(1), m.group(2)
        return ("\\makeatletter\\@ifundefined{%s}{\\%s{\\%s}}{}\\makeatother"
                % (name, cmd, name))
    return ALLOC_RE.subn(sub, s)


STRAY_BRACE_TAIL = re.compile(r"\n[ \t]*\}[ \t]*\n?\s*$")


def fix_stray_brace(path):
    r"""One unmatched } alone on the last line of an \input-ed fragment.

    esttab writes `\resizebox{\textwidth}{!}{` above the tabular and its brace
    below it. When the author moves the \resizebox into the parent file and
    forgets the closing brace here, the fragment carries one } too many. LaTeX
    recovers with "Extra }, or forgotten \endgroup" and the table survives, so
    the defect travels from Overleaf unnoticed — but it silently closes
    whatever group the parent had open around the \input.

    Only the unambiguous case is repaired: exactly one surplus }, and it is the
    file's last line. Returns True if it commented one out.
    """
    s = open(path, encoding="utf-8", errors="replace").read()
    body = re.sub(r"(?<!\\)%.*", "", re.sub(r"\\.", "", s))
    if body.count("}") - body.count("{") != 1:
        return False
    if not STRAY_BRACE_TAIL.search(s):
        return False
    s = STRAY_BRACE_TAIL.sub(
        lambda m: "\n%% [unmatched } removed by the import script — the group "
                  "it closed is opened in the file that \\input's this one]\n", s)
    open(path, "w", encoding="utf-8").write(s)
    return True


#: `x^2_i` is correct TeX; only the *same* index twice in a row is the mistake
DOUBLE_SUB = re.compile(r"([_^])\s*[A-Za-z0-9]\s*\1")


def check_double_subscripts(path):
    r"""Line numbers carrying `$Z_i_h_c_t$` — TeX reads only the first index.

    Reported, never repaired: `X_i_t` almost always means `X_{it}`, but it can
    also mean `X_{i_t}`, and the two are different variables.
    """
    bad = []
    for i, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
        stripped = re.sub(r"(?<!\\)%.*", "", line)
        for seg in re.split(r"(?<!\\)\$", stripped)[1::2]:
            if DOUBLE_SUB.search(seg):
                bad.append(i)
                break
    return bad


# ---------------------------------------------------------------------------
# 4. Namespacing: labels, refs and inputs
# ---------------------------------------------------------------------------

REF_COMMANDS = ["label", "ref", "eqref", "pageref", "autoref", "nameref",
                "cref", "Cref", "crefrange", "Crefrange"]


def prefix_refs(s, prefix):
    """Prefix every \\label / \\ref key, and normalise escaped underscores."""
    def brace(m):
        cmd, keys = m.group(1), m.group(2)
        out = []
        for k in keys.split(","):
            k = k.strip().replace("\\_", "_")
            out.append(k if k.startswith(prefix) else prefix + k)
        return "\\" + cmd + "{" + ",".join(out) + "}"

    s = re.sub(r"\\(" + "|".join(REF_COMMANDS) + r")\{([^{}]*)\}", brace, s)

    def bracket(m):
        k = m.group(1).strip().replace("\\_", "_")
        return "\\hyperref[" + (k if k.startswith(prefix) else prefix + k) + "]"

    return re.sub(r"\\hyperref\[([^\]]*)\]", bracket, s)


def prefix_inputs(s, root):
    """Make every \\input path relative to the thesis root instead of the paper."""
    def rep(m):
        cmd, path = m.group(1), m.group(2).strip()
        if path.startswith(root + "/") or path.startswith("/"):
            return m.group(0)
        return "\\" + cmd + "{" + root + "/" + path + "}"
    return re.sub(r"\\(input|include)\{([^{}]*)\}", rep, s)


LEVELS = ["section", "subsection", "subsubsection", "paragraph", "subparagraph"]
HEADING_RE = re.compile(r"(?<!\\)\\(sub)*(?:section|paragraph)(?=\*?\s*[\[{])")

#: the appendix's top heading has to land here for tex/chapN.tex's
#: \thesubsection to number it 1.A, 1.B, 2.A, ...
APPENDIX_TOP = 1                                     # LEVELS[1] == subsection


def heading_levels(s):
    """The set of heading depths used in s, 0 = \\section."""
    found = set()
    for m in HEADING_RE.finditer(s):
        name = m.group(0)[1:]
        if name.endswith("paragraph"):
            found.add(3 + name.count("sub"))         # paragraph, subparagraph
        else:
            found.add(name.count("sub"))             # section .. subsubsection
    return found


def shift_headings(s, shift):
    r"""Move every heading `shift` levels down (positive) or up (negative).

    Not a fixed demotion: a paper's appendix may open with \section, or with
    \subsection, or — after someone has already tidied it once — with
    \subsubsection. What matters in the thesis is where the *top* one lands,
    so the shift is computed per chapter from the shallowest level present.
    """
    if not shift:
        return s, 0

    def sub(m):
        name = m.group(0)[1:]
        if name.endswith("paragraph"):
            lvl = 3 + name.count("sub")
        else:
            lvl = name.count("sub")
        lvl = min(max(lvl + shift, 0), len(LEVELS) - 1)
        return "\\" + LEVELS[lvl]

    return HEADING_RE.subn(sub, s)


#: \subsubsection*{A.2 Additional Tables} — the author numbered the appendix by
#: hand *and* starred the heading so LaTeX would not number it again. Once the
#: thesis numbers it, both have to go, but which of the two the author meant to
#: keep is not something to decide for them.
MANUAL_APPENDIX_LABEL = re.compile(
    r"(?<!\\)\\(?:sub)*(?:section|paragraph)\*\s*\{\s*[A-Z]{1,2}(?:\.\d+)*\.?\s+")


def check_manual_appendix_labels(path):
    """Line numbers of starred appendix headings that carry their own A.1 label."""
    s = open(path, encoding="utf-8", errors="replace").read()
    return sorted({s.count("\n", 0, m.start()) + 1
                   for m in MANUAL_APPENDIX_LABEL.finditer(s)})


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def tex_files(base, skip=("_orig-overleaf",)):
    for dp, _, names in os.walk(base):
        if any(s in dp for s in skip):
            continue
        for n in sorted(names):
            if n.endswith(".tex"):
                yield os.path.join(dp, n)


def read_state(chapter_dir):
    p = os.path.join(chapter_dir, ".thesis-import.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_state(chapter_dir, state):
    p = os.path.join(chapter_dir, ".thesis-import.json")
    json.dump(state, open(p, "w", encoding="utf-8"), indent=2, sort_keys=True)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    what, target = sys.argv[1], sys.argv[2]
    if what == "bib":
        dropped, backup, empty = clean_bib(target)
        print("%s: %d fields and %d empty entries dropped (backup: %s)"
              % (target, dropped, empty, backup))
    elif what == "unicode":
        total = sum(fix_unicode(p) for p in tex_files(target))
        print("%s: %d control characters fixed" % (target, total))
    elif what == "caption":
        tb = to = tl = tn = 0
        for p in tex_files(target):
            b, o, l, n = fix_captions(p)
            if b or o or l or n:
                print("  %s: %d blank-line captions, %d orphan captions, "
                      "%d labels moved, %d stray \\newline" % (p, b, o, l, n))
            tb, to, tl, tn = tb + b, to + o, tl + l, tn + n
        print("%s: %d / %d / %d / %d" % (target, tb, to, tl, tn))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# 5. Image paths containing spaces
# ---------------------------------------------------------------------------

GRAPHICS = re.compile(r"(\\includegraphics(?:\[[^\]]*\])?\{)([^{}]*)\}")
IMG_EXT = ("", ".pdf", ".png", ".jpg", ".jpeg", ".eps")


def fix_spaced_graphics(chapter_dir):
    """Rename image files whose name contains a space and update the references.

    Spaces in a graphics path survive pdflatex but break Git, Overleaf uploads
    and most build scripts. Returns the number of files renamed.
    """
    renamed = {}
    for path in tex_files(chapter_dir):
        s = open(path, encoding="utf-8", errors="replace").read()
        for m in GRAPHICS.finditer(s):
            ref = m.group(2).strip()
            if " " not in ref:
                continue
            for ext in IMG_EXT:
                src = os.path.join(chapter_dir, ref + ext)
                dst = os.path.join(chapter_dir, ref.replace(" ", "_") + ext)
                if os.path.exists(src):
                    if src != dst and not os.path.exists(dst):
                        os.rename(src, dst)
                    renamed[ref] = ref.replace(" ", "_")
                    break
                if os.path.exists(dst):
                    #: already renamed on disk, only the reference lags behind
                    renamed[ref] = ref.replace(" ", "_")
                    break
    if not renamed:
        return 0
    for path in tex_files(chapter_dir):
        s = orig = open(path, encoding="utf-8", errors="replace").read()
        for old, new in renamed.items():
            s = s.replace(old, new)
        if s != orig:
            open(path, "w", encoding="utf-8").write(s)
    return len(renamed)


# ---------------------------------------------------------------------------
# 6. Macros defined in the paper's own preamble
# ---------------------------------------------------------------------------

def _balanced(s, i):
    """Consume a balanced {...} starting at the first { at or after i."""
    try:
        i = s.index("{", i)
    except ValueError:
        return None, i
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i:j + 1], j + 1
        j += 1
    return None, i


def extract_macros(preamble, provided_commands, provided_envs, colors=None):
    """Collect the paper's own \\newcommand / \\definecolor / \\newtheorem.

    Returns lines that are safe to drop into the thesis preamble:

    * \\newcommand becomes \\providecommand, so two chapters defining the same
      shorthand cannot clash (the first chapter wins);
    * anything the class or preamble-extra.tex already defines is skipped;
    * \\the<counter> definitions are skipped when the counter comes from a
      \\newtheorem in the same preamble — LaTeX defines those itself, and
      defining them twice is an error;
    * theorem environments are emitted before the commands that use them.
    """
    colors = {} if colors is None else colors
    theorems, commands, local_colors = [], [], {}

    #: counters LaTeX will create by itself, so \the<counter> must not be defined
    own_counters = set()
    for m in re.finditer(r"\\newtheorem\*?\s*\{([^{}]*)\}", preamble):
        own_counters.add(m.group(1))
    for m in re.finditer(r"\\newcounter\s*\{([^{}]*)\}", preamble):
        own_counters.add(m.group(1))

    for m in re.finditer(r"\\newtheorem(\*?)\s*\{([^{}]*)\}(\[[^\]]*\])?\s*\{([^{}]*)\}(\[[^\]]*\])?",
                         preamble):
        star, env, counter, label, parent = m.groups()
        if env in provided_envs:
            continue
        if star:
            #: \newtheorem* needs amsthm, which clashes with the class's `proof`.
            #: An unnumbered environment does the same job.
            body = ("\\newenvironment{%s}{\\par\\medskip\\noindent"
                    "\\textbf{%s.}\\itshape}{\\par\\medskip}" % (env, label))
        else:
            body = ("\\newtheorem{%s}%s{%s}%s"
                    % (env, counter or "", label, parent or ""))
        #: the name may already be taken by a package (hyphenat defines \hyp),
        #: so define it only if it is free — and only if the counter it hangs
        #: off was itself created, which is not the case when that one was
        #: skipped for the same reason.
        guard = "\\@ifundefined{%s}{%s}{}" % (env, body)
        dep = (counter or parent or "").strip("[]")
        if dep:
            guard = "\\@ifundefined{%s}{\\@ifundefined{c@%s}{}{%s}}{}" % (env, dep, body)
        theorems.append(guard)
        provided_envs.add(env)

    for m in re.finditer(r"\\(?:new|renew|provide)command\*?\s*\{?\\([A-Za-z@]+)\}?", preamble):
        name = m.group(1)
        if name in provided_commands:
            continue
        if name.startswith("the") and name[3:] in own_counters:
            continue
        j = m.end()
        opts = ""
        while j < len(preamble) and preamble[j] in " \t":
            j += 1
        while j < len(preamble) and preamble[j] == "[":
            k = preamble.index("]", j)
            opts += preamble[j:k + 1]
            j = k + 1
            while j < len(preamble) and preamble[j] in " \t":
                j += 1
        body, _ = _balanced(preamble, j)
        if body is None:
            continue
        commands.append("\\providecommand{\\%s}%s%s" % (name, opts, body))
        provided_commands.add(name)

    for m in re.finditer(r"\\DeclareMathOperator\*?\s*\{?\\([A-Za-z@]+)\}?", preamble):
        name = m.group(1)
        if name in provided_commands:
            continue
        body, _ = _balanced(preamble, m.end())
        if body is None:
            continue
        commands.append("\\DeclareMathOperator{\\%s}%s" % (name, body))
        provided_commands.add(name)

    # a paper often redefines the same colour twice; keep its last word on it
    for m in re.finditer(r"\\definecolor\s*\{([^{}]*)\}\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
                         preamble):
        local_colors[m.group(1)] = (m.group(2), m.group(3))

    color_lines, clashes = [], []
    for name, spec in local_colors.items():
        if name in colors:
            if colors[name] != spec:
                clashes.append(name)
            continue
        colors[name] = spec
        color_lines.append("\\definecolor{%s}{%s}{%s}" % (name, spec[0], spec[1]))

    return color_lines + theorems + commands, clashes


# ---------------------------------------------------------------------------
# 7. Unbalanced math delimiters
# ---------------------------------------------------------------------------

def check_math_delimiters(path):
    """Line numbers where a $ is opened and not closed on the same line.

    Inline math almost never spans a line break in practice, so an odd number
    of $ on one line is a reliable sign of a mangled table header — the kind
    Stata's esttab produces, e.g. `+ Viol.$\\times}`. Lines inside a display
    math environment are skipped, since those legitimately span lines.

    Only reports: repairing it needs a human, because only the author knows
    what the formula was meant to say.
    """
    DISPLAY_OPEN = ("\\begin{equation}", "\\begin{equation*}", "\\begin{align}",
                    "\\begin{align*}", "\\begin{gather}", "\\begin{gather*}",
                    "\\begin{multline}", "\\begin{eqnarray}", "\\[")
    DISPLAY_CLOSE = ("\\end{equation}", "\\end{equation*}", "\\end{align}",
                     "\\end{align*}", "\\end{gather}", "\\end{gather*}",
                     "\\end{multline}", "\\end{eqnarray}", "\\]")
    bad, display = [], 0
    for i, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
        stripped = re.sub(r"%.*$", "", re.sub(r"\\.", "", line))
        suspicious = display == 0 and stripped.count("$") % 2
        #: a $ opened inside a {...} cell and closed outside it is always wrong,
        #: and the count on the line as a whole can still come out even:
        #:     \multicolumn{1}{c}{+ Viol.$\times}
        if not suspicious and display == 0 and "$" in stripped:
            depth, start = 0, None
            for k, ch in enumerate(stripped):
                if ch == "{":
                    if depth == 0:
                        start = k
                    depth += 1
                elif ch == "}" and depth:
                    depth -= 1
                    if depth == 0 and stripped[start:k].count("$") % 2:
                        suspicious = True
                        break
        if suspicious:
            bad.append(i)
        for tok in DISPLAY_OPEN:
            display += line.count(tok)
        for tok in DISPLAY_CLOSE:
            display -= line.count(tok)
        display = max(display, 0)
    return bad


# ---------------------------------------------------------------------------
# 8. Paths whose case does not match the file on disk
# ---------------------------------------------------------------------------

INPUT_RE = re.compile(r"(\\(?:input|include)\{)([^{}]*)(\})")


def fix_path_case(chapter_dir, folder):
    """Make every \\input and \\includegraphics path match the real file name.

    macOS filesystems ignore case, so `\\input{Tables/x}` happily finds
    `tables/x` on the author's laptop and then fails on Overleaf, on Linux and
    in CI, which do not. This rewrites the reference to the name on disk.

    Returns (fixed, missing): how many paths were corrected, and the ones that
    match no file at all whatever the case.
    """
    #: Build the index from the directory listing, which keeps the real
    #: spelling. os.path.exists() is useless here: on macOS it answers yes to
    #: `Tables/x` when the folder is `tables/`, which is exactly the mistake
    #: this pass exists to catch.
    index, exact = {}, set()
    for dp, _, names in os.walk(chapter_dir):
        if "_orig-overleaf" in dp:
            continue
        for n in names:
            rel = os.path.relpath(os.path.join(dp, n), chapter_dir).replace(os.sep, "/")
            index.setdefault(rel.lower(), rel)
            exact.add(rel)

    fixed, missing = 0, []

    def resolve(rest, exts):
        """Real spelling of `rest` in this chapter, or None if already right."""
        for ext in exts:
            if rest + ext in exact:
                return None                       # already correct
        for ext in exts:
            hit = index.get((rest + ext).lower())
            if hit:
                return hit[:-len(ext)] if ext and hit.lower().endswith(ext) else hit
        return ""                                 # nowhere to be found

    def split_comment(line):
        """(code, comment) — a % that is not \% starts the comment."""
        esc = False
        for i, ch in enumerate(line):
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == "%":
                return line[:i], line[i:]
        return line, ""

    for path in tex_files(chapter_dir):
        orig = open(path, encoding="utf-8", errors="replace").read()

        def do_input(m):
            nonlocal fixed
            head, ref, tail = m.groups()
            prefix = folder + "/"
            if not ref.startswith(prefix):
                return m.group(0)
            rest = ref[len(prefix):]
            got = resolve(rest, (".tex", "") if not rest.endswith(".tex") else ("",))
            if got is None:
                return m.group(0)
            if got == "":
                missing.append(ref)
                return m.group(0)
            fixed += 1
            return head + prefix + got + tail

        def do_graphics(m):
            nonlocal fixed
            head, ref = m.group(1), m.group(2).strip()
            got = resolve(ref, IMG_EXT)
            if got is None:
                return m.group(0)
            if got == "":
                missing.append(ref)
                return m.group(0)
            fixed += 1
            return head + got + "}"

        #: only touch real code — a path inside a comment, or inside a
        #: \begin{comment} block, is not part of the document
        out, commented = [], False
        for line in orig.split("\n"):
            if "\\begin{comment}" in line:
                commented = True
            if "\\end{comment}" in line:
                commented = False
                out.append(line)
                continue
            if commented:
                out.append(line)
                continue
            code, comment = split_comment(line)
            code = INPUT_RE.sub(do_input, code)
            code = GRAPHICS.sub(do_graphics, code)
            out.append(code + comment)
        s = "\n".join(out)
        if s != orig:
            open(path, "w", encoding="utf-8").write(s)

    return fixed, sorted(set(missing))
