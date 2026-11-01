"""UNCTAD bilateral FDI statistics: listed only. No open bulk file or API; the UNCTADstat data centre is browser-only."""
import kg


def main():
    with kg.connect() as conn, conn.cursor() as cur:
        kg.add_source(cur, "unctad_fdi", name="UNCTAD bilateral FDI statistics", publisher="UNCTAD",
                      url="https://unctadstat.unctad.org/datacentre/dataviewer/US.FdiFlowsStock",
                      data_url="https://unctadstat-api.unctad.org/bulkdownload/US.FdiFlowsStock/CSV",
                      about="FDI flows and stocks by partner economy, 206 economies",
                      kinds=["flows"], coverage="Bilateral inflows, outflows, inward and outward stock; last published edition covers up to 2012",
                      access="registration", license="UNCTAD terms", found_by="survey")
        cur.execute("""UPDATE kg.sources SET status = 'listed',
                       status_note = 'no bilateral bulk file or open API: unctadstat-api bulkdownload returns HTTP 400 for US.FdiFlowsStock/CSV, the data viewer needs a browser session; IMF DIP covers the same bilateral positions'
                       WHERE slug = 'unctad_fdi'""")
        conn.commit()
    print("unctad_fdi  listed")


if __name__ == "__main__":
    main()
