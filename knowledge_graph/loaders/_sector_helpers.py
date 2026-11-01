"""Shared by the sector size loaders."""
import kg


def num(x):
    """Float from a source cell, None when blank or not a number."""
    try:
        v = float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def country_or_other(l, iso3=None, m49=None, name=None, prefix="src"):
    """Country place id; a source's own entity (former state, aggregate) becomes kind 'other'."""
    pid = l.country(iso3=iso3) if iso3 else None
    if not pid and m49 is not None:
        pid = l.country(m49=m49)
    if not pid and name:
        pid = l.country(name=name)
    if not pid and (iso3 or m49 is not None) and name:
        pid = l.other_place("%s:%s" % (prefix, iso3 or m49), name)
    return pid


class Unmatched(set):
    def report(self, slug):
        if self:
            print("%s  unmatched places: %s" % (slug, sorted(self)[:40]), flush=True)


def fao_place(l, code, m49, name):
    """FAOSTAT area to a place id. Regional aggregates (codes 5000 and up) return None; FAO's own non-ISO areas become kind 'other'."""
    if int(code) >= 5000:
        return None
    m = str(m49).lstrip("'")
    return l.country(m49=int(m)) if m.isdigit() and l.country(m49=int(m)) else l.other_place("fao:%s" % code, name)
