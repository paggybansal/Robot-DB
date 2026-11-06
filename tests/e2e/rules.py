"""Rule catalog - keep in sync with the GoRules / BRG definitions."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    rule_id: str
    group: str            # PRACTITIONER | PRACTICE | FACILITY
    description: str


_ALL = [
    # ---------------------------------------------------------- practitioner
    Rule("BRP_0021", "PRACTITIONER",
         "Practitioner Locations should have a primary location per GNPI/TIN combination"),
    Rule("BRP_0022", "PRACTITIONER",
         "Practitioner has more than 1 primary location per GNPI/TIN combination"),
    Rule("BRP_0036", "PRACTITIONER",
         "Practitioner Product with multiple contracts with overlapping dates "
         "(2 as PCP or 2 as Specialist)"),
    Rule("BRP_0037", "PRACTITIONER",
         "PODs, IPA, etc. Missing PODs for PCPs - PCP should have POD or IPA attached."),

    # ---------------------------------------------------------- practice
    Rule("BRG_0002", "PRACTICE",
         "Check if Date From is null for any of the Location Products from payload"),
    Rule("BRG_0020", "PRACTICE",
         "FQHCRHCNotPCPWithIPACheck"),

    # ---------------------------------------------------------- facility
    Rule("BRF_0005", "FACILITY",
         "Facility missing effective date on product"),
]

RULES = {r.rule_id: r for r in _ALL}


def get(rule_id: str):
    return RULES.get((rule_id or "").strip().upper())


def group_of(rule_id: str) -> str:
    r = get(rule_id)
    return r.group if r else ""


def description_of(rule_id: str) -> str:
    r = get(rule_id)
    return r.description if r else ""


def known_ids() -> list:
    return sorted(RULES)


def ids_for_group(group: str) -> list:
    g = (group or "").upper()
    return sorted(r.rule_id for r in _ALL if r.group == g)
