from acquittify.ontology.authority_extract import extract_authority_mentions


def test_extract_authorities_handles_federal_patterns() -> None:
    text = """
    Defendant was convicted under 18 U.S.C. § 1343 and 18 U.S.C. §§ 1341, 1343.
    The court considered Title 18, Section 3553(a)(2)(B), and a § 2255 motion.
    Agency rules included 21 C.F.R. § 1306.04(a) and 45 C.F.R. pt. 164.
    Procedure relied on Fed. R. Crim. P. 29, Rule 33 motion, and Fed. R. Evid. 404(b).
    The district court applied U.S.S.G. § 3B1.1(a) and Section 5K1.1 departure.
    Claims were asserted under Section 1983 and the Fifth Amendment.
    Constitutional authority also included U.S. Const. art. I, § 8, cl. 3 (the Commerce Clause).
    Congress enacted Pub. L. No. 115-391 and 98 Stat. 1837.
    """
    mentions = extract_authority_mentions(text)
    source_ids = {item.source_id for item in mentions}
    normalized = {item.normalized_text for item in mentions}

    assert "statute.usc.18" in source_ids
    assert "statute.usc.28" in source_ids
    assert "statute.usc.42" in source_ids

    assert "reg.cfr.21" in source_ids
    assert "reg.cfr.45" in source_ids
    assert "rule.federal.crim.29" in source_ids
    assert "rule.federal.evid.404_b" in source_ids

    assert "reg.ussg.3b1.1_a" in source_ids
    assert "reg.ussg.5k1.1" in source_ids

    assert "constitution.us.amendment.5" in source_ids
    assert "constitution.us.article.1.section.8.clause.3" in source_ids
    assert "statute.public_law.115-391" in source_ids
    assert "statute.statutes_at_large.98.1837" in source_ids

    assert "18 U.S.C. § 1343" in normalized
    assert "42 U.S.C. § 1983" in normalized
    assert "U.S. Const. amend. V" in normalized
    assert "U.S. Const. art. I, § 8, cl. 3 (Commerce Clause)" in normalized
