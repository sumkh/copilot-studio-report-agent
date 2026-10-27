"""Shared helpers for the report-development skill scripts.

Standard library only, so every script still runs if the sandbox lacks optional
packages. Scripts import this module from their own folder.
"""
import colorsys
import hashlib
import json
import os
import re
import sys

# ----------------------------------------------------------------------------
# JSON / text I/O
# ----------------------------------------------------------------------------

def load_json(path):
    with open(path, "rb") as f:
        return json.loads(decode_text(f.read()))


def dump_json(obj, path=None):
    text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    if path:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")


def decode_text(data):
    """Decode bytes that may be UTF-8 (with/without BOM) or UTF-16 LE/BE."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8")
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    if len(data) > 1 and data[1:2] == b"\x00" and data[0:1] != b"\x00":
        return data.decode("utf-16-le")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def canonical_hash(obj):
    """Stable SHA-256 of a JSON-serialisable object (used for confirmation gates)."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fail(message, code=1):
    sys.stderr.write("ERROR: " + message + "\n")
    sys.exit(code)


# ----------------------------------------------------------------------------
# Names
# ----------------------------------------------------------------------------

_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def safe_identifier(text, prefix="f"):
    """CLS-compliant identifier for RDL names (fields, textboxes, groups)."""
    s = _IDENT_RE.sub("_", str(text or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = prefix
    if not (s[0].isalpha()):
        s = prefix + "_" + s
    return s[:100]


class UniqueNamer:
    """Hands out report-wide unique names (RDL requires unique item names)."""

    def __init__(self):
        self.used = set()

    def __call__(self, text, prefix="item"):
        base = safe_identifier(text, prefix)
        name, i = base, 2
        while name.lower() in self.used:
            name = "%s_%d" % (base, i)
            i += 1
        self.used.add(name.lower())
        return name


# ----------------------------------------------------------------------------
# Colours
# ----------------------------------------------------------------------------

_HEX_RE = re.compile(r"^#?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")


def normalize_hex(value):
    """'FF1F4E78' / '1F4E78' / '#1f4e78' -> '#1F4E78'; anything else -> None."""
    if not value or not isinstance(value, str):
        return None
    m = _HEX_RE.match(value.strip())
    if not m:
        return None
    v = m.group(1).upper()
    if len(v) == 8:          # ARGB
        if v[:2] == "00" and v[2:] == "000000":
            return None      # fully transparent black = "no colour" in openpyxl
        v = v[2:]
    return "#" + v


def apply_tint(hex_color, tint):
    """Excel tint (-1..1) applied in HLS space, per ECMA-376."""
    if not hex_color or not tint:
        return hex_color
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = l * (1.0 + tint) if tint < 0 else l * (1.0 - tint) + tint
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), s)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def is_valid_color(value):
    return bool(value) and (normalize_hex(value) is not None or str(value).startswith("=")
                            or re.match(r"^[A-Za-z]+$", str(value)) is not None)


# ----------------------------------------------------------------------------
# Units (RDL measurements are emitted in whole points: Microsoft recommends
# points to avoid rounding that causes merged cells in Excel exports)
# ----------------------------------------------------------------------------

def excel_width_to_pt(width_chars):
    """Excel column width (characters of the default font) -> points."""
    if width_chars is None:
        width_chars = 8.43
    px = int(width_chars * 7 + 5 + 0.5)
    return round(px * 0.75)


def pt_to_excel_width(pt):
    px = pt / 0.75
    return max(1.0, round((px - 5) / 7.0, 2))


def pt(value):
    return "%dpt" % int(round(float(value)))


PAPER_SIZES_PT = {
    # openpyxl paperSize code: (name, width_pt, height_pt) portrait
    1: ("Letter", 612, 792),
    5: ("Legal", 612, 1008),
    8: ("A3", 842, 1191),
    9: ("A4", 595, 842),
    11: ("A5", 420, 595),
}


# ----------------------------------------------------------------------------
# Excel number format -> .NET format string (used by the RDL Format property)
# ----------------------------------------------------------------------------

_BUILTIN_DATE_FORMATS = {
    "mm-dd-yy": ("d", "Excel built-in short date (locale-dependent) mapped to .NET short date 'd'"),
    "m/d/yy h:mm": ("g", "Excel built-in date-time mapped to .NET general date 'g'"),
    "[h]:mm:ss": (None, "elapsed-time format has no .NET equivalent; value will show as a time"),
}


def _scan_format(section):
    """Split a format section into ('lit', text) and ('code', text) parts."""
    parts, buf, i = [], "", 0
    while i < len(section):
        ch = section[i]
        if ch == '"':
            j = section.find('"', i + 1)
            j = len(section) if j < 0 else j
            if buf:
                parts.append(("code", buf))
                buf = ""
            parts.append(("lit", section[i:j + 1]))
            i = j + 1
            continue
        if ch == "\\" and i + 1 < len(section):
            if buf:
                parts.append(("code", buf))
                buf = ""
            parts.append(("lit", section[i:i + 2]))
            i += 2
            continue
        if ch in "_*" and i + 1 < len(section):
            i += 2           # padding / fill characters have no .NET meaning
            continue
        buf += ch
        i += 1
    if buf:
        parts.append(("code", buf))
    return parts


def _split_sections(fmt):
    sections, buf, in_q, depth = [], "", False, 0
    for ch in fmt:
        if ch == '"':
            in_q = not in_q
        elif not in_q and ch == "[":
            depth += 1
        elif not in_q and ch == "]":
            depth = max(0, depth - 1)
        if ch == ";" and not in_q and depth == 0:
            sections.append(buf)
            buf = ""
        else:
            buf += ch
    sections.append(buf)
    return sections


_DATE_LETTERS = set("dmyhsDMYHS")


def _convert_date_code(code, has_ampm):
    out, i, tokens = [], 0, []
    while i < len(code):
        ch = code[i]
        up = code[i:i + 5].upper()
        if up.startswith("AM/PM"):
            tokens.append(("ampm", "tt"))
            i += 5
            continue
        if up.startswith("A/P"):
            tokens.append(("ampm", "t"))
            i += 3
            continue
        if ch in _DATE_LETTERS:
            j = i
            while j < len(code) and code[j].lower() == ch.lower():
                j += 1
            tokens.append((ch.lower(), j - i))
            i = j
            continue
        if ch == "0" and tokens and tokens[-1][0] == "frac":
            tokens[-1] = ("frac", tokens[-1][1] + 1)
            i += 1
            continue
        if ch == "." and i + 1 < len(code) and code[i + 1] == "0" and tokens and tokens[-1][0] == "s":
            tokens.append(("sep", "."))
            tokens.append(("frac", 0))
            i += 1
            continue
        tokens.append(("sep", ch))
        i += 1
    date_idx = [k for k, t in enumerate(tokens) if t[0] in ("d", "m", "y", "h", "s")]
    for k, (kind, val) in enumerate(tokens):
        if kind == "sep":
            out.append(val)
        elif kind == "ampm":
            out.append(val)
        elif kind == "frac":
            out.append("f" * max(1, val))
        elif kind == "d":
            out.append("d" * min(val, 4))
        elif kind == "y":
            out.append("yy" if val <= 2 else "yyyy")
        elif kind == "h":
            out.append(("h" if has_ampm else "H") * min(val, 2))
        elif kind == "s":
            out.append("s" * min(val, 2))
        elif kind == "m":
            pos = date_idx.index(k)
            prev_kind = tokens[date_idx[pos - 1]][0] if pos > 0 else None
            next_kind = tokens[date_idx[pos + 1]][0] if pos + 1 < len(date_idx) else None
            minute = prev_kind == "h" or next_kind == "s"
            if minute:
                out.append("m" * min(val, 2))
            else:
                out.append("M" * min(val, 4))
    return "".join(out)


def excel_numfmt_to_dotnet(fmt):
    """Convert an Excel number format code to a .NET format string.

    Returns (format_or_None, notes). None means "no Format property" (General/text).
    """
    notes = []
    if fmt is None:
        return None, notes
    fmt = str(fmt).strip()
    if fmt == "" or fmt.lower() == "general":
        return None, notes
    if fmt == "@":
        return None, ["text format (no Format property needed)"]
    if fmt in _BUILTIN_DATE_FORMATS:
        res, note = _BUILTIN_DATE_FORMATS[fmt]
        return res, [note]
    sections = _split_sections(fmt)
    if len(sections) > 3:
        notes.append("text section of the Excel format was dropped")
        sections = sections[:3]
    out = []
    for sec in sections:
        # Locale/currency tokens like [$$-409] or [$€-x-euro2]
        sec = re.sub(r"\[\$([^\]\-]*)(?:-[^\]]*)?\]",
                     lambda m: ('"%s"' % m.group(1)) if m.group(1) else "", sec)
        if re.search(r"\[(?:Red|Black|Blue|Cyan|Green|Magenta|White|Yellow|Color\s*\d+)\]", sec, re.I):
            notes.append("colour inside the number format was dropped; use a Color expression instead")
            sec = re.sub(r"\[(?:Red|Black|Blue|Cyan|Green|Magenta|White|Yellow|Color\s*\d+)\]", "", sec, flags=re.I)
        if re.search(r"\[[<>=][^\]]*\]", sec):
            notes.append("conditional section in the number format was dropped")
            sec = re.sub(r"\[[<>=][^\]]*\]", "", sec)
        parts = _scan_format(sec)
        code_text = "".join(t for k, t in parts if k == "code")
        stripped = re.sub(r"[Ee][+-]", "", code_text)
        is_date = any(c in _DATE_LETTERS for c in stripped) and not re.search(r"[0#?]", re.sub(r"\.0+", "", stripped))
        if "/" in code_text and "?" in code_text:
            notes.append("fraction formats are not supported in .NET; exported as decimal")
            return None, notes
        has_ampm = "AM/PM" in code_text.upper() or "A/P" in code_text.upper()
        res = []
        for kind, text in parts:
            if kind == "lit":
                res.append(text)
            elif is_date:
                res.append(_convert_date_code(text, has_ampm))
            else:
                if "?" in text:
                    notes.append("'?' digit placeholder replaced with '#'")
                    text = text.replace("?", "#")
                if "@" in text:
                    text = text.replace("@", "")
                res.append(text)
        out.append("".join(res).strip())
    if len(out) == 3 and '"' in out[2] and not re.search(r"[0.]", re.sub(r'"[^"]*"', "", out[2])):
        out[2] = out[2].replace("#", "").strip()    # accounting zero section: "-"?? -> "-"
    result = ";".join(out).strip(";")
    return (result or None), sorted(set(notes))


# ----------------------------------------------------------------------------
# Connection strings and Power Query (M) sources
# ----------------------------------------------------------------------------

_SECRET_KEYS = ("password", "pwd", "accountkey", "sharedaccesskey", "secret", "token", "sig")


def parse_conn_string(text):
    """'A=1;B="x;y"' -> {'a': '1', 'b': 'x;y'} (keys lower-cased)."""
    result, key, val, in_q, reading_key = {}, "", "", None, True
    for ch in (text or "") + ";":
        if reading_key:
            if ch == "=":
                reading_key = False
            elif ch == ";":
                if key.strip():
                    result[key.strip().lower()] = ""
                key = ""
            else:
                key += ch
        else:
            if in_q:
                if ch == in_q:
                    in_q = None
                else:
                    val += ch
            elif ch in "\"'" and not val.strip():
                in_q = ch
            elif ch == ";":
                result[key.strip().lower()] = val.strip()
                key, val, reading_key = "", "", True
            else:
                val += ch
    return result


def mask_secrets(conn):
    """Return (masked_string, found_secret)."""
    if not conn:
        return conn, False
    found = False

    def repl(m):
        nonlocal found
        found = True
        return m.group(1) + "=***"

    pattern = r"(?i)\b(" + "|".join(_SECRET_KEYS) + r")\s*=\s*(\"[^\"]*\"|'[^']*'|[^;]*)"
    return re.sub(pattern, repl, conn), found


def classify_connection(provider, conn):
    """Best-effort description of a data source from provider + connection string."""
    props = parse_conn_string(conn or "")
    provider_u = (provider or "").upper()
    ds = props.get("data source", "")
    catalog = props.get("initial catalog", "")
    info = {"provider": provider, "server": ds or None, "database": catalog or None}
    if provider_u == "PBIDATASET" or "pbiazure://" in ds.lower():
        info["kind"] = "powerbi_semantic_model"
        m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", catalog)
        info["model_id"] = m.group(1) if m else None
        idp = props.get("identity provider", "")
        t = re.findall(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", idp)
        info["tenant_id"] = t[-1] if t else None
    elif ds.lower().startswith("powerbi://"):
        info["kind"] = "powerbi_xmla"
        info["workspace"] = ds.rstrip("/").split("/")[-1]
        info["model_name"] = catalog or None
        m = re.search(r"semanticmodelid=([0-9a-fA-F-]{36})", conn or "", re.I)
        info["model_id"] = m.group(1) if m else None
    elif provider_u in ("SQL", "SQLAZURE", "SQLPDW", "MSSQL") or "provider=sqloledb" in (conn or "").lower():
        info["kind"] = "sql"
    elif provider_u in ("OLEDB", "ODBC", "ORACLE", "TERADATA", "SNOWFLAKE", "DATAVERSE", "SQLAS", "OLEDB-MD", "ESSBASE", "SHAREPOINTLIST", "XML", "ENTERDATA"):
        info["kind"] = provider_u.lower()
    else:
        info["kind"] = "other"
    return info


_M_SOURCE_FUNCS = {
    "Sql.Database", "Sql.Databases", "AnalysisServices.Database", "AnalysisServices.Databases",
    "PowerBI.Dataflows", "PowerPlatform.Dataflows", "Excel.Workbook", "Csv.Document", "File.Contents",
    "Folder.Files", "Folder.Contents", "SharePoint.Files", "SharePoint.Contents", "SharePoint.Tables",
    "OData.Feed", "Web.Contents", "Odbc.DataSource", "Odbc.Query", "OleDb.DataSource", "OleDb.Query",
    "Oracle.Database", "Snowflake.Databases", "Databricks.Catalogs", "DatabricksMultiCloud.Catalogs",
    "GoogleBigQuery.Database", "AmazonRedshift.Database", "PostgreSQL.Database", "MySQL.Database",
    "Teradata.Database", "SapHana.Database", "SapBusinessWarehouse.Cubes", "CommonDataService.Database",
    "Dataverse.Contents", "Lakehouse.Contents", "Warehouse.Contents", "Fabric.Warehouse",
    "AzureStorage.Blobs", "AzureStorage.DataLake", "AzureDataExplorer.Contents", "Value.NativeQuery",
    "Salesforce.Data", "Salesforce.Reports", "Json.Document", "Xml.Tables",
}
_CALL_RE = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+)\s*\(")


def _read_call_args(text, start):
    """Given index just after '(', return (list_of_raw_args, end_index)."""
    args, buf, depth, i, in_str = [], "", 0, start, False
    while i < len(text):
        ch = text[i]
        if in_str:
            buf += ch
            if ch == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    buf += '"'
                    i += 1
                else:
                    in_str = False
        elif ch == '"':
            in_str = True
            buf += ch
        elif ch in "([{":
            depth += 1
            buf += ch
        elif ch in ")]}":
            if depth == 0 and ch == ")":
                args.append(buf.strip())
                return args, i
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            args.append(buf.strip())
            buf = ""
        else:
            buf += ch
        i += 1
    args.append(buf.strip())
    return args, i


def _m_literal(arg):
    if len(arg) >= 2 and arg[0] == '"' and arg[-1] == '"':
        return arg[1:-1].replace('""', '"')
    return None


def m_sources(m_code, query_name=None):
    """Extract data-source function calls with their literal arguments from M code."""
    found = []
    for m in _CALL_RE.finditer(m_code or ""):
        func = m.group(1)
        if func not in _M_SOURCE_FUNCS and not re.search(r"\.(Database|Databases|Contents|Catalogs|Feed)$", func):
            continue
        args, _ = _read_call_args(m_code, m.end())
        literal_args = []
        options = {}
        for a in args:
            lit = _m_literal(a)
            if lit is not None:
                literal_args.append(lit)
            elif a.startswith("["):
                for k, v in re.findall(r'(\w+)\s*=\s*("(?:[^"]|"")*")', a):
                    options[k] = _m_literal(v)
            elif a:
                literal_args.append("<expr: %s>" % a[:60])
        entry = {"function": func, "args": literal_args}
        if options:
            entry["options"] = options
        if query_name:
            entry["query"] = query_name
        found.append(entry)
    return found


def m_shared_queries(section_m):
    """Split a 'section Section1; shared Q = ...;' document into {name: code}."""
    queries = {}
    for m in re.finditer(r'shared\s+(#"(?:[^"]|"")+"|[A-Za-z_][\w.]*)\s*=', section_m or ""):
        name = m.group(1)
        if name.startswith('#"'):
            name = name[2:-1].replace('""', '"')
        start = m.end()
        nxt = re.search(r";\s*(?:\r?\n)+\s*shared\s", section_m[start:])
        end = start + nxt.start() if nxt else len(section_m)
        queries[name] = section_m[start:end].strip().rstrip(";")
    return queries
