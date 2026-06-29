"""Shared loader for the donor information registry (data/donor_info.json).

The registry augments AEC-disclosed donor names with a link to the donor's own
website or social media and a short, sourced description of who they are, so
readers can see what the source of a donation actually is. It is keyed by the
exact donor string as disclosed to the AEC (the same entity can appear under
several spellings; each spelling gets its own entry, optionally sharing text).

Used by both build_candidates.py (member return donors) and
build_party_donations.py (party donors) to attach an "info" object to each
donor entry at build time, so the data stays rebuild-safe.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "data", "donor_info.json")

# fields copied onto each donor entry's "info" object (kept light for the front end)
_FIELDS = ("link", "link_type", "description", "category")


def load():
    """Return {donor name: info dict}. Empty if the registry is absent."""
    if not os.path.exists(PATH):
        return {}
    with open(PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("donors", data) if isinstance(data, dict) else {}


def info_for(name, registry):
    """Return a light info object for a donor name, or None if not in the registry."""
    rec = registry.get(name.strip()) if name else None
    if not rec:
        return None
    out = {k: rec[k] for k in _FIELDS if rec.get(k)}
    return out or None
