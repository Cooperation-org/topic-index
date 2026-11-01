"""OECD DAC Creditor Reporting System: ODA by donor, recipient, purpose and year, 2010 on, from the open SDMX API."""
import csv
import io
import re
import time
import urllib.error

import kg
from loaders._money_helpers import Countries, fetch, sdmx_codelist

BASE = "https://sdmx.oecd.org/dcd-public/rest/"
DATAFLOW = "OECD.DCD.FSD,DSD_CRS@DF_CRS,1.7"
# DONOR.RECIPIENT.SECTOR.MEASURE.CHANNEL.MODALITY.FLOW_TYPE.PRICE_BASE.MD_DIM.MD_ID.UNIT_MEASURE
# measure 100 = ODA, aggregate (not project) rows, current prices, USD millions
KEY = ".%s..100._T._T.D+C.V._T..USD"
FIRST_YEAR = 2010
LEAF_DONOR = re.compile(r"^\d[A-Z]{2,4}\d{2,3}$")  # 1UN014, 4EU001, 5WB002: one agency, not a group


def main():
    l = kg.Loader("oecd_crs", name="Creditor Reporting System (CRS), ODA by purpose", publisher="OECD DAC",
                  url="https://data-explorer.oecd.org/?lc=en&df[ds]=dsDisplayAndQueryTool&df[id]=DSD_CRS%40DF_CRS",
                  data_url=BASE, kinds=["flows"],
                  about="Official development assistance by donor, recipient country and DAC purpose code, commitments and gross disbursements",
                  coverage="DAC members, non-DAC donors and multilateral agencies to recipient countries, 2010 on", access="open",
                  license="OECD terms, https://www.oecd.org/en/about/terms-conditions.html", found_by="survey")
    disb = l.measure("aid_disbursed_usd", "ODA gross disbursements, USD", "USD", "aid",
                     about="from = donor country or agency (multilaterals are imf-style oecd: places), to = recipient country, or an oecd: bucket for unspecified within a region; DAC purpose code in sector; current prices, ODA (measure 100), gross disbursements, aggregate rows. Only 5-digit purpose codes stored, roll up by sector path")
    comm = l.measure("aid_committed_usd", "ODA commitments, USD", "USD", "aid",
                     about="from = donor country or agency, to = recipient country or unspecified bucket; DAC purpose code in sector; current prices, ODA (measure 100), commitments")
    d = kg.workdir("oecd_crs")
    xml = open(kg.download(BASE + "dataflow/OECD.DCD.FSD/DSD_CRS@DF_CRS/1.7?references=descendants", d / "crs.xml"), "rb").read()
    areas = sdmx_codelist(xml, "CL_AREA_ORG")
    sectors = sdmx_codelist(xml, "CL_DAC_SECTOR")
    cs = Countries(l)
    sec_ids = {}

    def sector(code):
        if code not in sec_ids:
            name, parent = sectors[code]
            sec_ids[code] = l.sector("dac_purpose", code, name, parent=sector(parent) if parent in sectors and parent not in ("_T", "1000") else None)
        return sec_ids[code]

    recips = [(p, p) for p in sorted({c for c in areas if len(c) == 3 and c.isalpha() and l.country(iso3=c)})]
    recips += [(c, c) for c in sorted(areas) if c.endswith("_X")]
    for code, _ in recips:
        if l.done(code):
            continue
        time.sleep(3)
        try:
            body = fetch("%sdata/%s/%s?startPeriod=%d" % (BASE, DATAFLOW, KEY % code, FIRST_YEAR),
                         headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}, raw=True)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            body = b""
        with l.part(code):
            to = l.country(iso3=code) or l.other_place("oecd:" + code, areas[code][0])
            agg = {}
            for r in csv.DictReader(io.StringIO(body.decode("utf-8"))):
                s = r["SECTOR"]
                if not (len(s) == 5 and s.isdigit()) or s not in sectors or not r["OBS_VALUE"]:
                    continue
                donor = r["DONOR"]
                frm = l.country(iso3=donor) if len(donor) == 3 else None
                if not frm and LEAF_DONOR.match(donor) and donor in areas:
                    frm = l.other_place("oecd:" + donor, areas[donor][0])
                if not frm:
                    continue
                k = (frm, int(r["TIME_PERIOD"]), r["FLOW_TYPE"], s)
                agg[k] = agg.get(k, 0) + float(r["OBS_VALUE"]) * 1e6
            for (frm, year, flow, s), v in agg.items():
                l.flow(disb if flow == "D" else comm, year, frm, to, sector(s), v)
    l.finish()
    kg.cleanup("oecd_crs")


if __name__ == "__main__":
    main()
