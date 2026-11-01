"""Country shapes for the page: Natural Earth 1:110m, only the code and name kept."""
import json
import urllib.request

import kg

URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson"


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": kg.UA})
    src = json.load(urllib.request.urlopen(req, timeout=120))
    feats = [{"type": "Feature", "geometry": f["geometry"],
              "properties": {"iso3": f["properties"]["ISO_A3_EH"], "name": f["properties"]["NAME"]}}
             for f in src["features"]]
    (kg.HERE / "web/static/countries.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))


if __name__ == "__main__":
    main()
