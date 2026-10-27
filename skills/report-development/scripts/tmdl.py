"""TMDL (Tabular Model Definition Language) helpers: quoting, emitting and a light parser.

Follows the syntax documented at https://learn.microsoft.com/analysis-services/tmdl/tmdl-overview:
tab indentation (object, properties one level deeper, multi-line expressions one level deeper
than properties), names in single quotes when they contain . = : ' or whitespace, `///`
descriptions, `= expression` default properties, ``` blocks for verbatim expressions.
"""
import re

_PLAIN_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Columns of the generated Power Query date table: name, dataType, formatString, hidden, sortByColumn
DATE_COLUMNS = [
    ("Date", "dateTime", "Short Date", False, None),
    ("Year", "int64", "0", False, None),
    ("Quarter", "string", None, False, None),
    ("Month Number", "int64", "0", True, None),
    ("Month", "string", None, False, "Month Number"),
    ("Year Month Number", "int64", "0", True, None),
    ("Month Year", "string", None, False, "Year Month Number"),
]
KEYWORDS = {"table", "column", "measure", "partition", "relationship", "expression", "role", "hierarchy", "level",
            "annotation", "ref", "model", "database", "culture", "perspective", "queryGroup", "dataSource",
            "calculationGroup", "calculationItem", "function", "tablePermission", "extendedProperty",
            "linguisticMetadata", "variation", "formatStringDefinition", "detailRowsDefinition"}


def name(n):
    """Object name, quoted when needed (anything but letters, digits and underscores)."""
    n = str(n)
    if _PLAIN_NAME.match(n) and n not in KEYWORDS:
        return n
    return "'%s'" % n.replace("'", "''")


def qualified(table, column):
    return "%s.%s" % (name(table), name(column))


def value(v):
    """Property value: quote when it has leading/trailing whitespace or double quotes."""
    s = str(v)
    if s != s.strip() or '"' in s or s == "":
        return '"%s"' % s.replace('"', '""')
    return s


def expression_block(expr, level):
    """Lines for a multi-line expression at the given tab level (no trailing whitespace)."""
    lines = str(expr).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    # remove common leading indentation, keep relative indentation (as spaces)
    expanded = [l.replace("\t", "    ").rstrip() for l in lines]
    widths = [len(l) - len(l.lstrip(" ")) for l in expanded if l.strip()]
    cut = min(widths) if widths else 0
    return ["\t" * level + l[cut:] if l.strip() else "" for l in expanded]


def dax_default(expr, obj_level):
    """Render a DAX default expression: same line when single-line, else on the following lines."""
    s = str(expr).strip()
    if "\n" not in s and "\r" not in s:
        return " = " + s, []
    return " =", expression_block(s, obj_level + 2)


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------

def _indent(line):
    n = 0
    for ch in line:
        if ch == "\t":
            n += 1
        else:
            break
    if n == 0 and line.startswith("    "):
        n = (len(line) - len(line.lstrip(" "))) // 4
    return n


def split_name(text):
    """Parse a (possibly quoted) name at the start of text; return (name, rest)."""
    text = text.strip()
    if text.startswith("'"):
        i, out = 1, ""
        while i < len(text):
            if text[i] == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    out += "'"
                    i += 2
                    continue
                return out, text[i + 1:].strip()
            out += text[i]
            i += 1
        return out, ""
    m = re.match(r"^([^\s=:'.]+)(.*)$", text)
    return (m.group(1), m.group(2).strip()) if m else (text, "")


def split_qualified(text):
    """'Sales'.'Order Date' or Sales.OrderDate -> (table, column)."""
    t, rest = split_name(text)
    if rest.startswith("."):
        c, _ = split_name(rest[1:])
        return t, c
    return None, t


def _collect_expression(lines, i, base_indent, first):
    """Collect a default/property expression starting after '='. Returns (text, next_index)."""
    first = first.strip()
    if first.startswith("```"):
        body = []
        i += 1
        while i < len(lines) and lines[i].strip() != "```":
            body.append(lines[i])
            i += 1
        return "\n".join(l.strip("\t") for l in body), i + 1
    if first:
        return first, i + 1
    body = []
    i += 1
    while i < len(lines) and (not lines[i].strip() or _indent(lines[i]) >= base_indent + 2):
        body.append(lines[i])
        i += 1
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(l.strip() for l in body), i


def parse(files):
    """Parse TMDL documents ({path: text}) into a plain dict model description."""
    model = {"database": {"name": None, "properties": {}}, "model": {"properties": {}}, "tables": {},
             "relationships": [], "expressions": {}, "roles": []}
    for _path, text in files.items():
        lines = text.replace("\r\n", "\n").split("\n")
        i, table, obj, obj_kind, obj_indent, desc = 0, None, None, None, 0, []
        while i < len(lines):
            raw = lines[i]
            s = raw.strip()
            if not s:
                i += 1
                continue
            ind = _indent(raw)
            if s.startswith("///"):
                desc.append(s[3:].strip())
                i += 1
                continue
            word = s.split(None, 1)[0]
            rest = s[len(word):].strip()
            description = " ".join(desc) or None
            desc = []
            if ind == 0:
                table = None
                if word == "database":
                    obj_kind, obj = "database", model["database"]
                    model["database"]["name"] = split_name(rest)[0] if rest else None
                elif word == "model":
                    obj_kind, obj = "model", model["model"]
                elif word == "table":
                    tname, _ = split_name(rest)
                    table = model["tables"].setdefault(tname, {"name": tname, "columns": {}, "measures": {}, "partitions": [],
                                                               "properties": {}, "description": description})
                    obj_kind, obj = "table", table
                elif word == "relationship":
                    obj = {"name": split_name(rest)[0], "properties": {}}
                    model["relationships"].append(obj)
                    obj_kind = "relationship"
                elif word == "expression":
                    ename, after = split_name(rest)
                    text_, i = _collect_expression(lines, i, 0, after[1:] if after.startswith("=") else "")
                    obj = model["expressions"].setdefault(ename, {"name": ename, "expression": text_, "properties": {},
                                                                  "description": description})
                    obj_kind, obj_indent = "expression", 0
                    continue
                else:
                    if word == "role":
                        model["roles"].append(split_name(rest)[0])
                    obj_kind, obj = word, {"properties": {}}
                obj_indent = 0
                i += 1
                continue
            if table is not None and ind == 1 and word in ("column", "measure", "partition", "hierarchy", "calculationGroup"):
                oname, after = split_name(rest)
                if word in ("column", "measure"):
                    expr = None
                    if after.startswith("="):
                        expr, i = _collect_expression(lines, i, 1, after[1:])
                    else:
                        i += 1
                    o = {"name": oname, "expression": expr, "properties": {}, "description": description}
                    (table["columns"] if word == "column" else table["measures"])[oname] = o
                    obj_kind, obj, obj_indent = word, o, 1
                    continue
                if word == "partition":
                    obj = {"name": oname, "type": after[1:].strip() if after.startswith("=") else None, "properties": {}, "source": None}
                    table["partitions"].append(obj)
                    obj_kind, obj_indent = "partition", 1
                else:
                    obj_kind, obj, obj_indent = word, {"properties": {}}, 1
                i += 1
                continue
            if obj is not None and ind == obj_indent + 1 and word != "annotation":
                if obj_kind == "partition" and re.match(r"^source\s*=", s):
                    obj["source"], i = _collect_expression(lines, i, obj_indent, s.split("=", 1)[1])
                    continue
                if ":" in s:
                    k, v = s.split(":", 1)
                    v = v.strip()
                    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                        v = v[1:-1].replace('""', '"')
                    obj["properties"][k.strip()] = v
                elif re.match(r"^[A-Za-z]+$", s):
                    obj["properties"][s] = "true"
            i += 1
    return model


# ----------------------------------------------------------------------------
# DAX references
# ----------------------------------------------------------------------------

_STR = re.compile(r'"(?:[^"]|"")*"')
_QUALIFIED = re.compile(r"(?:'((?:[^']|'')+)'|([A-Za-z_][A-Za-z0-9_]*))\s*\[([^\]]+)\]")
_BRACKET = re.compile(r"\[([^\]]+)\]")


def dax_references(expr):
    """Return (qualified [(table, column)], unqualified [name]) referenced by a DAX expression."""
    s = _STR.sub('""', expr or "")
    s = re.sub(r"--[^\n]*|//[^\n]*", "", s)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    qualified_refs = []
    spans = []
    for m in _QUALIFIED.finditer(s):
        t = (m.group(1) or m.group(2)).replace("''", "'")
        qualified_refs.append((t, m.group(3)))
        spans.append((m.start(3) - 1, m.end(3) + 1))
    bare = []
    for m in _BRACKET.finditer(s):
        if any(a <= m.start() and m.end() <= b for a, b in spans):
            continue
        bare.append(m.group(1))
    tables = [t.replace("''", "'") for t in re.findall(r"'((?:[^']|'')+)'(?!\s*\[)", s)]
    return qualified_refs, bare, tables


def dax_syntax_problem(expr):
    s = _STR.sub('""', expr or "")
    if s.count('"') % 2:
        return "unbalanced double quotes"
    depth = 0
    for ch in s:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth < 0:
            return "closing parenthesis without opening one"
    if depth:
        return "unbalanced parentheses"
    if s.count("[") != s.count("]"):
        return "unbalanced square brackets"
    return None
