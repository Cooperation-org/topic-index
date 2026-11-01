"""Harmonized System 2022 as kg.sectors scheme hs: section > 2-digit > 4-digit > 6-digit. Adds codes BACI uses that the list lacks."""
import csv
import io

import kg

BASE = "https://raw.githubusercontent.com/datasets/harmonized-system/main/data/"
BACI = "https://www.cepii.fr/DATA_DOWNLOAD/baci/data/BACI_HS22_V202601.zip"


def main():
    l = kg.Loader("hs_codes", name="Harmonized System 2022 product tree",
                  publisher="World Customs Organization, via datasets/harmonized-system",
                  url="https://github.com/datasets/harmonized-system", data_url=BASE + "harmonized-system.csv",
                  kinds=["sectors"], about="Product classification tree: 21 sections, 97 chapters, 1229 headings, about 5600 six-digit codes; path prefixes roll up",
                  coverage="HS 2022 edition", access="open", license="ODC-PDDL-1.0", found_by="core")
    if l.done("tree"):
        return finish(l)
    d = kg.workdir("hs_codes")
    sections = {r["section"]: r["name"] for r in csv.DictReader(open(kg.download(BASE + "sections.csv", d / "sections.csv"), encoding="utf-8-sig"))}
    rows = [r for r in csv.DictReader(open(kg.download(BASE + "harmonized-system.csv", d / "hs.csv"), encoding="utf-8"))
            if r["level"] in ("2", "4", "6") and r["hscode"] != "TOTAL"]
    sections["TOTAL"] = "Commodities not specified according to kind"  # the list's section for chapter 99
    ids = {s: l.sector("hs", s, name) for s, name in sections.items()}
    section_of = {}
    with l.part("tree"):
        for level in ("2", "4", "6"):
            for r in rows:
                if r["level"] != level:
                    continue
                code = r["hscode"]
                if level == "2":
                    section_of[code] = r["section"]
                    parent = ids[r["section"]]
                else:
                    parent = ids[r["parent"]]
                ids[code] = l.sector("hs", code, r["description"], parent=parent)
        # codes BACI reports that the list lacks (HS22 BACI reports 271000 for all of 2710 below crude)
        z = kg.download(BACI, kg.workdir("baci_hs22") / "baci.zip")
        for r in kg.zip_csv(z, "product_codes_HS22_V202601.csv"):
            code = r["code"]
            if code not in ids:
                ids[code] = l.sector("hs", code, r["description"], parent=ids[code[:4]])
                print("added from BACI:", code, flush=True)
        l.conn.commit()
    finish(l)
    kg.cleanup("hs_codes")


def finish(l):
    l.cur.execute("SELECT count(*) FROM kg.sectors WHERE scheme = 'hs'")
    n = l.cur.fetchone()[0]
    l.finish("%d sectors" % n)
    l.cur.execute("UPDATE kg.sources SET row_count = %s WHERE id = %s", (n, l.source_id))
    l.conn.commit()


if __name__ == "__main__":
    main()
