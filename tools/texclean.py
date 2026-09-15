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


def clean_bib(path):
    """Drop noisy fields and escape % & # . Returns (dropped, backup_path)."""
    src = open(path, encoding="utf-8", errors="replace").read()
    backup = path + ".orig"
    if not os.path.exists(backup):
        open(backup, "w", encoding="utf-8").write(src)

    out, i, dropped = [], 0, 0
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
        out.append(head + ",".join(kept) + "\n}")
        i = j + 1

    open(path, "w", encoding="utf-8").write("".join(out))
    return dropped, backup


# ---------------------------------------------------------------------------
# 2. Windows-1252 control characters
# ---------------------------------------------------------------------------

C1_REMAP = {0x91: "\u2018", 0x92: "\u2019", 0x93: "\u201c", 0x94: "\u201d",
            0x96: "--", 0x97: "---", 0x85: "\\dots ", 0x95: "\u2022",
            0xA0: " "}


def fix_unicode(path):
    """Replace stray Windows-1252 control bytes. Returns how many."""
    s = open(path, encoding="utf-8", errors="replace").read()
    out, hits = [], 0
    for ch in s:
        o = ord(ch)
        if o in C1_REMAP:
            out.append(C1_REMAP[o])
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


def fix_captions(path):
    """Three caption/label defects. Returns (blank_lines, orphans, labels, newlines)."""
    s = orig = open(path, encoding="utf-8", errors="replace").read()
    s, blanks = _fix_blank_lines_in_captions(s)
    s, orphans = _comment_orphan_captions(s)
    s, labels = LABEL_IN_TABULAR.subn(lambda m: m.group("lab") + m.group("beg"), s)
    s, newlines = VERTICAL_NEWLINE.subn(
        "\n\n%% [\\\\newline in vertical mode removed by the import script]\n", s)
    if s != orig:
        open(path, "w", encoding="utf-8").write(s)
    return blanks, orphans, labels, newlines


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


def demote_headings(s):
    """\\section -> \\subsection -> \\subsubsection -> \\paragraph."""
    s = s.replace("\\subsubsection", "\x00")
    s = s.replace("\\subsection", "\\subsubsection")
    s = s.replace("\\section", "\\subsection")
    return s.replace("\x00", "\\paragraph")


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
        dropped, backup = clean_bib(target)
        print("%s: %d fields dropped (backup: %s)" % (target, dropped, backup))
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
