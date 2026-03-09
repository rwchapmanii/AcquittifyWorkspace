from acquittify_taxonomy import TAXONOMY_SET, HIERARCHY


def test_asset_forfeiture_codes_present():
    expected_codes = [
        "FCD.ISS.ASSET_FORFEITURE.SEIZURE_RESTRAINT",
        "FCD.ISS.ASSET_FORFEITURE.CRIMINAL_FORFEITURE",
        "FCD.ISS.ASSET_FORFEITURE.CIVIL_FORFEITURE",
        "FCD.ISS.ASSET_FORFEITURE.ADMINISTRATIVE",
        "FCD.ISS.ASSET_FORFEITURE.ANCILLARY",
        "FCD.ISS.ASSET_FORFEITURE.SUBSTITUTE_ASSETS",
        "FCD.ISS.ASSET_FORFEITURE.INTERNATIONAL",
        "FCD.ISS.ASSET_FORFEITURE.EQUITABLE_SHARING",
        "FCD.ISS.ASSET_FORFEITURE.FEES_COSTS",
        "FCD.ISS.ASSET_FORFEITURE.DISPOSITION",
    ]
    for code in expected_codes:
        assert code in TAXONOMY_SET


def test_asset_forfeiture_hierarchy_present():
    asset_forfeiture = HIERARCHY["ISS"]["ASSET_FORFEITURE"]
    assert "CIVIL_FORFEITURE" in asset_forfeiture
    assert "CRIMINAL_FORFEITURE" in asset_forfeiture
    assert "SEIZURE_RESTRAINT" in asset_forfeiture
