from acquittify.citation_utils import has_citations


def test_has_citations_detects_case() -> None:
    assert has_citations("United States v. Smith, 123 F.2d 235 (9th Cir. 2001)")


def test_has_citations_detects_statute() -> None:
    assert has_citations("18 U.S.C. § 1951")


def test_has_citations_detects_regulation() -> None:
    assert has_citations("28 C.F.R. § 0.0")


def test_has_citations_detects_treatise() -> None:
    assert has_citations("Wright & Miller, Federal Practice and Procedure")


def test_has_citations_rejects_plain_text() -> None:
    assert not has_citations("No citations here.")
