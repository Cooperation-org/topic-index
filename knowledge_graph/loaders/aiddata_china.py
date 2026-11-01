"""AidData Global Chinese Development Finance Dataset 3.0: Chinese official finance by project, recipient, sector and location."""
import csv
import io
import zipfile

import openpyxl

import kg
from loaders._money_helpers import Countries

URL = "https://docs.aiddata.org/ad4/datasets/AidDatas_Global_Chinese_Development_Finance_Dataset_Version_3_0.zip"
DIR = "AidDatas_Global_Chinese_Development_Finance_Dataset_Version_3_0/"
XLSX = DIR + "AidDatasGlobalChineseDevelopmentFinanceDataset_v3.0.xlsx"
ADM1 = DIR + "ADM Location Data/GCDF_3.0_ADM1_Locations.csv"
CLASS_MEASURES = {  # flow class: (slug, name)
    "ODA-like": ("china_oda_like_usd", "Chinese ODA-like finance committed, USD"),
    "OOF-like": ("china_oof_like_usd", "Chinese OOF-like finance committed, USD"),
    "Vague (Official Finance)": ("china_vague_official_usd", "Chinese finance of unclear type committed, USD"),
}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    l = kg.Loader("aiddata_china", name="Global Chinese Development Finance Dataset 3.0", publisher="AidData at William & Mary",
                  url="https://www.aiddata.org/data/aiddatas-global-chinese-development-finance-dataset-version-3-0",
                  data_url=URL, kinds=["flows", "entities", "links"],
                  about="Chinese government loans and grants by project: recipient, sector, amount, agencies, status, subnational location",
                  coverage="China to recipient countries, commitments 2000 to 2021", access="open",
                  license="CC BY 4.0 (AidData, see License sheet)", found_by="survey")
    cs = Countries(l)
    d = kg.workdir("aiddata_china")
    z = zipfile.ZipFile(kg.download(URL, d / "gcdf.zip"))
    ws = openpyxl.load_workbook(z.open(XLSX), read_only=True)["GCDF_3.0"]
    it = ws.iter_rows(values_only=True)
    head = [h for h in next(it) if h]
    rows = [dict(zip(head, r)) for r in it if r[0] is not None]
    china = l.country(iso3="CHN")
    mids = {c: l.measure(slug, name, "USD", "finance",
                         about="from = China (financier), to = recipient country or region bucket (aiddata: place), by commitment year, nominal USD, sector in aiddata_sector, only records AidData recommends for aggregates (no umbrella double counting)")
            for c, (slug, name) in CLASS_MEASURES.items()}

    def recipient(r):
        iso3 = r["Recipient ISO-3"]
        return (iso3 and l.country(iso3=iso3)) or l.other_place("aiddata:" + r["Recipient"], r["Recipient"])

    if not l.done("flows"):
        with l.part("flows"):
            agg = {}
            for r in rows:
                amt, cls, year = num(r["Amount (Nominal USD)"]), r["Flow Class"], r["Commitment Year"]
                if r["Recommended For Aggregates"] != "Yes" or amt is None or cls not in mids or not year:
                    continue
                sec = l.sector("aiddata_sector", r["Sector Code"], r["Sector Name"]) if r["Sector Code"] else None
                k = (cls, int(year), recipient(r), sec)
                agg[k] = agg.get(k, 0) + amt
            for (cls, year, to, sec), v in agg.items():
                l.flow(mids[cls], year, china, to, sec, v)
    ents = {}
    if not l.done("projects"):
        with l.part("projects"):
            for r in rows:
                sec = l.sector("aiddata_sector", r["Sector Code"], r["Sector Name"]) if r["Sector Code"] else None
                attrs = {k: v for k, v in {
                    "title": r["Title"], "status": r["Status"], "intent": r["Intent"], "flow_type": r["Flow Type"],
                    "flow_class": r["Flow Class"], "commitment_year": r["Commitment Year"], "completion_year": r["Completion Year"],
                    "amount_nominal_usd": num(r["Amount (Nominal USD)"]), "funding_agencies": r["Funding Agencies"],
                    "implementing_agencies": r["Implementing Agencies"], "receiving_agencies": r["Direct Receiving Agencies"],
                    "recommended_for_aggregates": r["Recommended For Aggregates"],
                }.items() if v is not None}
                l.entity(r["AidData Record ID"], r["Title"] or r["AidData Record ID"], "project", place_id=recipient(r),
                         sector_id=sec, attrs=attrs)
            l.conn.commit()
    if not l.done("locations"):
        l.cur.execute("SELECT ext_id, id FROM kg.entities WHERE source_id = %s", (l.source_id,))
        ents = dict(l.cur.fetchall())
        l.cur.execute("SELECT p.iso3, a.id, a.name, a.alt_names FROM kg.places a JOIN kg.places p ON p.id = a.parent_id WHERE a.kind = 'admin1'")
        adm = {}
        for iso3, pid, name, alt in l.cur.fetchall():
            for n in [name] + list(alt or []):
                adm.setdefault((iso3, n.lower()), pid)
        year = {r["AidData Record ID"]: r["Commitment Year"] for r in rows}
        with l.part("locations"):
            for r in csv.DictReader(io.TextIOWrapper(z.open(ADM1), encoding="utf-8-sig", newline="")):
                eid = ents.get(r["id"])
                if not eid:
                    continue
                place = adm.get((r["shapeGroup"], r["shapeName"].lower()))
                attrs = {"adm1": r["shapeName"], "lat": num(r["centroid_latitude"]), "lon": num(r["centroid_longitude"]),
                         "share": num(r["even_split_ratio"])}
                to = place or l.country(iso3=r["shapeGroup"])
                if to:
                    l.link("located_in", eid, to_place=to, year=int(year[r["id"]]) if year.get(r["id"]) else None,
                           value=num(r["even_split_ratio_commitment_value"]), unit="USD", attrs=attrs)
    cs.report()
    l.finish()
    kg.cleanup("aiddata_china")


if __name__ == "__main__":
    main()
