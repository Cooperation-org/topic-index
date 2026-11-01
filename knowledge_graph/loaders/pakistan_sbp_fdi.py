"""State Bank of Pakistan FDI by country and sector, from the published PDFs. Blocked: sbp.org.pk answers 403 or an HTML shell."""
import kg

URLS = ["https://www.sbp.org.pk/ecodata/NetInflow.pdf", "https://www.sbp.org.pk/ecodata/NetinflowSummary.pdf"]


def main():
    l = kg.Loader("pakistan_sbp_fdi", name="State Bank of Pakistan: foreign direct investment by country and sector",
                  publisher="State Bank of Pakistan", url="https://www.sbp.org.pk/ecodata/index2.asp", data_url=URLS[0],
                  about="Net FDI inflow into Pakistan by investing country and by sector, monthly and fiscal year", kinds=["flows"],
                  coverage="Pakistan, fiscal years", access="open", license="SBP terms", found_by="survey")
    d = kg.workdir("pakistan_sbp_fdi")
    for i, url in enumerate(URLS):
        try:
            path = kg.download(url, d / ("sbp%d.pdf" % i))
        except Exception as e:
            note = "download failed: %s" % e
            continue
        if path.read_bytes()[:5] == b"%PDF-":
            break
        path.unlink()
        note = "sbp.org.pk returns an HTML page, not the PDF, for %s (HTTP 200 shell, 403 on the site root)" % url
    else:
        l.fail(note + "; invest.gov.pk/statistics unreachable from this host")
        print("pakistan_sbp_fdi  failed:", note)
        return
    raise NotImplementedError("a PDF was served; add the pdfplumber parse once its layout can be read")


if __name__ == "__main__":
    main()
