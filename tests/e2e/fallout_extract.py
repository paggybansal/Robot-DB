"""
Pull rule ids and identifiers out of arbitrary PDQA / DL response shapes.

Nothing assumes a fixed schema - it walks dicts/lists and matches on key names
plus a BRx_nnnn regex, so it survives response format changes.
"""
from __future__ import annotations

import re

from e2e_excel import norm

RULE_RE = re.compile(r"\b(BR[PGF])[_\-]?(\d{3,4})\b", re.IGNORECASE)

RULE_KEY_NAMES = {"ruleid", "ruleids", "rulecode", "businessruleid", "brid",
                  "validationrule", "rulename", "errorcode", "code"}

NPI_KEYS    = ("nationalProviderID", "npi", "providerNPI", "individualNPI")
GNPI_KEYS   = ("groupNPI", "gnpi", "organizationNPI", "groupNationalProviderID")
TAXID_KEYS  = ("taxID", "taxId", "tin", "taxIdentificationNumber", "federalTaxID")
SYMPLR_KEYS = ("symplrID", "symplrId", "symplr_id", "symplrProviderID",
               "sourceSystemID", "providerID", "entityID")

_NPI_OK   = lambda v: v.isdigit() and len(v) == 10
_TAXID_OK = lambda v: v.isdigit() and len(v) == 9


# --------------------------------------------------------------------------- rules
def _canon(prefix: str, digits: str) -> str:
    return f"{prefix.upper()}_{int(digits):04d}"


def extract_rule_ids(*objects) -> list:
    """Every BRx_nnnn rule id found anywhere in the given objects (ordered, unique)."""
    found, seen = [], set()

    def _add(text):
        for prefix, digits in RULE_RE.findall(str(text)):
            rid = _canon(prefix, digits)
            if rid not in seen:
                seen.add(rid)
                found.append(rid)

    def _walk(obj):
        if obj is None:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower().replace("_", "") in RULE_KEY_NAMES:
                    if isinstance(v, (list, tuple)):
                        for item in v:
                            _add(item)
                    else:
                        _add(v)
                _walk(v)
        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                _walk(item)
        else:
            _add(obj)

    for o in objects:
        _walk(o)
    return found


# --------------------------------------------------------------------------- ids
def _deep_find(obj, key_candidates, validator=None) -> str:
    wanted = {k.lower().replace("_", "") for k in key_candidates}
    stack = [obj]
    while stack:
        cur = stack.pop(0)
        if isinstance(cur, dict):
            for k, v in cur.items():
                if str(k).lower().replace("_", "") in wanted:
                    val = norm(v)
                    if val and (validator is None or validator(val)):
                        return val
                if isinstance(v, (dict, list, tuple)):
                    stack.append(v)
        elif isinstance(cur, (list, tuple)):
            stack.extend(x for x in cur if isinstance(x, (dict, list, tuple)))
    return ""


def extract_identifiers(*sources) -> dict:
    """Best-effort NPI / GNPI / TAXID / SYMPLR ID from payload, DL response, symplr result."""
    out = {"npi": "", "gnpi": "", "taxid": "", "symplr_id": ""}
    for src in sources:
        if src is None:
            continue
        out["npi"]       = out["npi"]       or _deep_find(src, NPI_KEYS, _NPI_OK)
        out["gnpi"]      = out["gnpi"]      or _deep_find(src, GNPI_KEYS, _NPI_OK)
        out["taxid"]     = out["taxid"]     or _deep_find(src, TAXID_KEYS, _TAXID_OK)
        out["symplr_id"] = out["symplr_id"] or _deep_find(src, SYMPLR_KEYS)
    return out
