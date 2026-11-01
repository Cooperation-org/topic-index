"""Open Supply Hub: the facilities API answers 401 without an account token, so it is listed, not loaded."""
from loaders._entity_helpers import list_only


def main():
    list_only("open_supply_hub", "facilities API returns 401 without a free account token (opensupplyhub.org/api/facilities); not loaded",
              name="Open Supply Hub", publisher="Open Supply Hub", url="https://opensupplyhub.org/",
              data_url="https://opensupplyhub.org/api/facilities/", kinds=["entities", "links"],
              about="Factories and production facilities worldwide with names, addresses, coordinates and the brands that source from them",
              coverage="World", access="free-key", license="ODbL", found_by="core")


if __name__ == "__main__":
    main()
