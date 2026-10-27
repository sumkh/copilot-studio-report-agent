"""Validate RDL against the RDL 2016/01 XSD and PBIR JSON against Microsoft's published JSON schemas.

Test-only helper (needs lxml + jsonschema). Point it at local copies of the schemas:
  RDL_XSD          path to ReportDefinition 2016/01 XSD (from the MS-RDL open specification, section 5.8)
  PBIR_SCHEMA_DIR  folder mirroring https://github.com/microsoft/json-schemas (contains fabric/...)
"""
import json
import os
import zipfile

PREFIX = "https://developer.microsoft.com/json-schemas/"


def validate_rdl(path, xsd_path):
    from lxml import etree
    schema = etree.XMLSchema(etree.parse(xsd_path))
    doc = etree.parse(path)
    ok = schema.validate(doc)
    return ok, [str(e) for e in schema.error_log][:20]


def _registry(schema_dir):
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT7
    resources = []
    for base, _, files in os.walk(schema_dir):
        for f in files:
            if not f.endswith(".json"):
                continue
            full = os.path.join(base, f)
            rel = os.path.relpath(full, schema_dir).replace(os.sep, "/")
            with open(full, encoding="utf-8") as fh:
                doc = json.load(fh)
            res = Resource.from_contents(doc, default_specification=DRAFT7)
            resources.append((PREFIX + rel, res))
            if doc.get("$id") and doc["$id"] != PREFIX + rel:
                resources.append((doc["$id"], res))
    return Registry().with_resources(resources)


def validate_pbir_files(files, schema_dir):
    """files: {path: parsed_json}. Returns {path: [errors]} (empty list = valid, None = no local schema)."""
    import jsonschema
    registry = _registry(schema_dir)
    results = {}
    for path, doc in files.items():
        url = doc.get("$schema") if isinstance(doc, dict) else None
        if not url or not url.startswith(PREFIX):
            continue
        try:
            schema = registry.contents(url)
        except Exception:
            results[path] = None
            continue
        v = jsonschema.Draft7Validator(schema, registry=registry)
        results[path] = ["%s: %s" % ("/".join(map(str, e.absolute_path)), e.message[:300]) for e in v.iter_errors(doc)][:10]
    return results


def load_pbip_zip(path):
    files = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.endswith((".json", ".pbir", ".pbip", ".platform")):
                try:
                    files[n] = json.loads(z.read(n).decode("utf-8-sig"))
                except Exception:
                    pass
    return files
