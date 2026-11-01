"""Company datasets that need registration or payment, or a key we do not hold: catalog rows only, nothing loaded."""
from loaders._entity_helpers import list_only

ROWS = {
    "opencorporates": dict(name="OpenCorporates", publisher="OpenCorporates", url="https://opencorporates.com/",
                           data_url="https://api.opencorporates.com/", access="paid",
                           about="Company registry records from over 140 jurisdictions", license="ODbL for open data; commercial licence otherwise"),
    "opensanctions": dict(name="OpenSanctions", publisher="OpenSanctions", url="https://www.opensanctions.org/",
                          data_url="https://www.opensanctions.org/datasets/", access="paid",
                          about="Sanctioned people, companies and politically exposed persons; bulk data free for non-commercial use only",
                          license="CC BY-NC 4.0, commercial licence on request"),
    "dun_bradstreet": dict(name="Dun and Bradstreet", publisher="Dun and Bradstreet", url="https://www.dnb.com/",
                           data_url="https://directplus.documentation.dnb.com/", access="paid",
                           about="Company records with D-U-N-S numbers, family trees, industry and revenue", license="commercial"),
    "orbis": dict(name="Orbis", publisher="Moody's Bureau van Dijk", url="https://www.bvdinfo.com/en-gb/our-products/data/international/orbis",
                  data_url="https://www.bvdinfo.com/", access="paid",
                  about="Ownership structures and financials for companies worldwide", license="commercial"),
    "panjiva": dict(name="Panjiva", publisher="S&P Global Market Intelligence", url="https://panjiva.com/",
                    data_url="https://panjiva.com/", access="paid",
                    about="Shipment records linking importers and suppliers from customs data", license="commercial"),
}


def main():
    for slug, fields in ROWS.items():
        list_only(slug, "%s access; catalog row only, not loaded" % fields["access"], kinds=["entities", "links"],
                  coverage="World", found_by="core", **fields)


if __name__ == "__main__":
    main()
