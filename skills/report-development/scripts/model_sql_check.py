#!/usr/bin/env python3
"""Generate a T-SQL query that recomputes a model's measures from its SQL sources, for validation.

Usage:
  python model_sql_check.py spec_model.json --group "Region[Region],Product[Category]"
         --measures "Total Units,Total Sales,Total Cost" [--date-from 2026-09-01 --date-to 2026-09-30]
         [--filter "Region[Region]=EMEA"] [--alias "Category=Product Category" ...] [--out check.sql]

Before the user refreshes and publishes a new semantic model, the model's numbers can only be
checked at the source. This script follows the model spec: the fact table and its relationships
become joins, Date-table columns become date expressions on the related fact column, and simple
measures translate to SQL aggregates:
  SUM/MIN/MAX/AVERAGE/COUNT/DISTINCTCOUNT('T'[C]), COUNTROWS(T), [Other measure],
  DIVIDE(a, b[, alt]), + - * /, parentheses and numbers.
Other DAX (CALCULATE, time intelligence, iterators) is reported as not translatable; check those
measures after publishing, with DAX through Fabric IQ.
Run the printed query with the SQL query tool (read-only), save the result as CSV and compare it
with the sample using reconcile.py.
"""
import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportkit as rk  # noqa: E402
import tmdl  # noqa: E402

AGG = {"SUM": "SUM", "MIN": "MIN", "MAX": "MAX", "AVERAGE": "AVG", "COUNT": "COUNT", "DISTINCTCOUNT": "COUNT"}


class NotTranslatable(Exception):
    pass


def tokenize(expr):
    s = expr
    tokens, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch.isspace():
            i += 1
        elif ch == "'":
            j = i + 1
            while j < len(s):
                if s[j] == "'" and (j + 1 >= len(s) or s[j + 1] != "'"):
                    break
                j += 2 if s[j] == "'" else 1
            tokens.append(("table", s[i + 1:j].replace("''", "'")))
            i = j + 1
        elif ch == "[":
            j = s.index("]", i)
            tokens.append(("bracket", s[i + 1:j]))
            i = j + 1
        elif ch.isdigit() or (ch == "." and i + 1 < len(s) and s[i + 1].isdigit()):
            m = re.match(r"\d*\.?\d+(?:[eE][-+]?\d+)?", s[i:])
            tokens.append(("number", m.group(0)))
            i += len(m.group(0))
        elif ch.isalpha() or ch == "_":
            m = re.match(r"[A-Za-z_][A-Za-z0-9_.]*", s[i:])
            tokens.append(("ident", m.group(0)))
            i += len(m.group(0))
        elif ch in "()+-*/,":
            tokens.append((ch, ch))
            i += 1
        else:
            raise NotTranslatable("unsupported character %r" % ch)
    return tokens


class Translator:
    def __init__(self, spec, fact_alias, col_sql, measures):
        self.spec, self.fact_alias, self.col_sql, self.measures = spec, fact_alias, col_sql, measures
        self.stack = []

    def measure(self, name):
        m = self.measures.get(name.lower())
        if not m:
            raise NotTranslatable("[%s] isn't a measure" % name)
        if name.lower() in self.stack:
            raise NotTranslatable("measure [%s] refers to itself" % name)
        self.stack.append(name.lower())
        try:
            self.toks, self.pos = tokenize(m["expression"]), 0
            saved = (self.toks, self.pos)
            out = self.expr()
            if self.pos != len(self.toks):
                raise NotTranslatable("unexpected text in [%s]" % name)
            return out
        finally:
            self.stack.pop()

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else (None, None)

    def take(self, kind=None):
        t = self.peek()
        if kind and t[0] != kind:
            raise NotTranslatable("expected %s" % kind)
        self.pos += 1
        return t

    def expr(self):
        out = self.term()
        while self.peek()[0] in ("+", "-"):
            op = self.take()[0]
            out = "(%s %s %s)" % (out, op, self.term())
        return out

    def term(self):
        out = self.factor()
        while self.peek()[0] in ("*", "/"):
            op = self.take()[0]
            rhs = self.factor()
            out = "(%s * %s)" % (out, rhs) if op == "*" else "(CAST(%s AS float) / NULLIF(%s, 0))" % (out, rhs)
        return out

    def column_ref(self):
        kind, val = self.take()
        if kind in ("table", "ident"):
            col = self.take("bracket")[1]
            return self.col_sql(val, col)
        raise NotTranslatable("expected a column reference")

    def factor(self):
        kind, val = self.peek()
        if kind == "number":
            self.take()
            return val
        if kind == "-":
            self.take()
            return "(-%s)" % self.factor()
        if kind == "(":
            self.take()
            inner = self.expr()
            self.take(")")
            return inner
        if kind == "bracket":
            self.take()
            saved = (self.toks, self.pos)
            sql = self.measure(val)
            self.toks, self.pos = saved
            return "(%s)" % sql
        if kind == "ident":
            fn = val.upper()
            self.take()
            self.take("(")
            if fn in AGG:
                ref = self.column_ref()
                self.take(")")
                return "COUNT(DISTINCT %s)" % ref if fn == "DISTINCTCOUNT" else "%s(%s)" % (AGG[fn], ref)
            if fn == "COUNTROWS":
                self.take()
                self.take(")")
                return "COUNT(*)"
            if fn == "DIVIDE":
                a = self.expr()
                self.take(",")
                b = self.expr()
                alt = "NULL"
                if self.peek()[0] == ",":
                    self.take()
                    alt = self.expr()
                self.take(")")
                return "(CASE WHEN (%s) = 0 OR (%s) IS NULL THEN %s ELSE CAST(%s AS float) / (%s) END)" % (b, b, alt, a, b)
            raise NotTranslatable("function %s isn't translated" % fn)
        raise NotTranslatable("unexpected token %r" % (val,))


def qident(name):
    return "[%s]" % str(name).replace("]", "]]")


def source_sql(t):
    src = t["source"]
    if src.get("query"):
        return "(%s)" % src["query"].strip().rstrip(";")
    return "%s.%s" % (qident(src.get("schema", "dbo")), qident(src["object"]))


def parse_ref(text):
    m = re.match(r"^\s*'?([^'\[]+?)'?\s*\[([^\]]+)\]\s*$", text)
    if not m:
        rk.fail("can't read column reference %r (use Table[Column])" % text)
    return m.group(1).strip(), m.group(2).strip()


def build_sql(spec, groups, measure_names, date_from=None, date_to=None, filters=(), aliases=None):
    aliases = aliases or {}
    tables = {t["name"].lower(): t for t in spec["tables"]}
    measures = {m["name"].lower(): m for m in spec.get("measures") or []}
    dt = spec.get("date_table") or {}
    date_name = (dt.get("name", "Date") if dt.get("create") else None)
    homes = {measures[m.lower()]["table"].lower() for m in measure_names if m.lower() in measures}
    missing = [m for m in measure_names if m.lower() not in measures]
    if missing:
        rk.fail("unknown measures: %s" % ", ".join(missing))
    if len(homes) != 1:
        rk.fail("the measures live in several tables (%s); check one fact table at a time" % ", ".join(sorted(homes)))
    fact = tables[homes.pop()]
    joins, aliases_by_table = [], {fact["name"].lower(): "f"}

    def join_to(tname):
        key = tname.lower()
        if key in aliases_by_table:
            return aliases_by_table[key]
        rel = next((r for r in spec.get("relationships") or [] if r.get("active", True)
                    and r["from_table"].lower() == fact["name"].lower() and r["to_table"].lower() == key), None)
        if not rel:
            rk.fail("no active relationship from %s to %s; only direct fact-to-dimension joins are supported" % (fact["name"], tname))
        dim = tables[key]
        alias = "d%d" % (len(joins) + 1)
        fc = next(c for c in fact["columns"] if c["name"].lower() == rel["from_column"].lower())
        dc = next(c for c in dim["columns"] if c["name"].lower() == rel["to_column"].lower())
        joins.append("LEFT JOIN %s AS %s ON f.%s = %s.%s" % (source_sql(dim), alias, qident(fc["source_column"]), alias, qident(dc["source_column"])))
        aliases_by_table[key] = alias
        return alias

    def date_column():
        rel = next((r for r in dt.get("relationships") or [] if r["table"].lower() == fact["name"].lower() and r.get("active", True)), None)
        if not rel:
            rk.fail("the fact table has no active relationship to the date table")
        c = next(c for c in fact["columns"] if c["name"].lower() == rel["column"].lower())
        return "f." + qident(c["source_column"])

    def col_sql(tname, cname):
        if date_name and tname.lower() == date_name.lower():
            d = date_column()
            exprs = {"date": "CAST(%s AS date)" % d, "year": "YEAR(%s)" % d, "month number": "MONTH(%s)" % d,
                     "quarter": "'Q' + CAST(DATEPART(QUARTER, %s) AS varchar(1))" % d,
                     "month": "LEFT(DATENAME(MONTH, %s), 3)" % d,
                     "year month number": "(YEAR(%s) * 100 + MONTH(%s))" % (d, d),
                     "month year": "LEFT(DATENAME(MONTH, %s), 3) + ' ' + CAST(YEAR(%s) AS varchar(4))" % (d, d)}
            if cname.lower() not in exprs:
                raise NotTranslatable("date column %s isn't translated" % cname)
            return exprs[cname.lower()]
        t = tables.get(tname.lower())
        if not t:
            raise NotTranslatable("unknown table %s" % tname)
        c = next((c for c in t["columns"] if c["name"].lower() == cname.lower()), None)
        if not c:
            raise NotTranslatable("unknown column %s[%s]" % (tname, cname))
        if c.get("expression"):
            raise NotTranslatable("calculated column %s[%s] isn't translated" % (tname, cname))
        alias = "f" if t is fact else join_to(t["name"])
        return "%s.%s" % (alias, qident(c["source_column"]))

    tr = Translator(spec, "f", col_sql, measures)
    select, group_by, notes = [], [], []
    for g in groups:
        tname, cname = parse_ref(g)
        expr = col_sql(tname, cname)
        select.append("%s AS %s" % (expr, qident(aliases.get(cname, cname))))
        group_by.append(expr)
    for m in measure_names:
        try:
            select.append("%s AS %s" % (tr.measure(m), qident(aliases.get(m, m))))
        except NotTranslatable as e:
            notes.append("[%s] can't be recomputed in SQL (%s); check it after publishing with DAX" % (m, e))
    where = []
    if date_from or date_to:
        d = date_column()
        for label, v in (("from", date_from), ("to", date_to)):
            if v:
                datetime.date.fromisoformat(v)          # validates the format
        if date_from and date_to:
            where.append("CAST(%s AS date) BETWEEN '%s' AND '%s'" % (d, date_from, date_to))
        elif date_from:
            where.append("CAST(%s AS date) >= '%s'" % (d, date_from))
        else:
            where.append("CAST(%s AS date) <= '%s'" % (d, date_to))
    for f in filters:
        left, value = f.split("=", 1)
        tname, cname = parse_ref(left)
        where.append("%s = N'%s'" % (col_sql(tname, cname), value.strip().replace("'", "''")))
    if not [s for s in select if s not in group_by]:
        rk.fail("nothing to compute")
    sql = ["SELECT", "    " + ",\n    ".join(select), "FROM %s AS f" % source_sql(fact)] + joins
    if where:
        sql.append("WHERE " + "\n  AND ".join(where))
    if group_by:
        sql.append("GROUP BY " + ", ".join(group_by))
        sql.append("ORDER BY " + ", ".join(group_by))
    return "\n".join(sql) + ";", notes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--group", default="", help="comma-separated Table[Column] list")
    ap.add_argument("--measures", required=True)
    ap.add_argument("--date-from")
    ap.add_argument("--date-to")
    ap.add_argument("--filter", action="append", default=[])
    ap.add_argument("--alias", action="append", default=[], help="'Name=Output column name', repeatable")
    ap.add_argument("--out")
    a = ap.parse_args()
    spec = rk.load_json(a.spec)
    if spec.get("report_type") != "semantic_model":
        rk.fail("model_sql_check.py works on semantic model specs")
    groups = [g.strip() for g in re.split(r",(?![^\[]*\])", a.group) if g.strip()]
    aliases = dict(x.split("=", 1) for x in a.alias)
    sql, notes = build_sql(spec, groups, [m.strip() for m in a.measures.split(",") if m.strip()],
                           a.date_from, a.date_to, a.filter, aliases)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(sql + "\n")
    print(sql)
    for n in notes:
        print("-- NOTE: " + n)


if __name__ == "__main__":
    main()
