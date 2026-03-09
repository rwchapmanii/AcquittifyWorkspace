from acquittify.ontology.circuit_origin import extract_originating_circuit, normalize_originating_circuit


def test_extract_originating_circuit_from_certiorari_line() -> None:
    text = (
        "SUPREME COURT OF THE UNITED STATES\n"
        "ON WRIT OF CERTIORARI TO THE UNITED STATES COURT OF APPEALS FOR THE NINTH CIRCUIT\n"
        "No. 00-0000."
    )
    code, label = extract_originating_circuit(text)
    assert code == "ca9"
    assert label == "Ninth Circuit"


def test_extract_originating_circuit_dc_variant() -> None:
    text = "CERTIORARI TO THE UNITED STATES COURT OF APPEALS FOR THE DISTRICT OF COLUMBIA CIRCUIT"
    code, label = extract_originating_circuit(text)
    assert code == "cadc"
    assert label == "D.C. Circuit"


def test_normalize_originating_circuit_variants() -> None:
    assert normalize_originating_circuit("ca6") == "ca6"
    assert normalize_originating_circuit("6th") == "ca6"
    assert normalize_originating_circuit("Sixth Circuit") == "ca6"
    assert normalize_originating_circuit("ELEV ENTH CIRCUIT") == "ca11"
