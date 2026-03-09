import re


def has_citations(text: str) -> bool:
    content = text or ""
    patterns = [
        r"\bv\.\s",  # case citation
        r"\bU\.S\.C\.\b|\bU\.S\.\b|\b§\b",  # statutes
        r"C\.F\.R\.",  # regulations
        r"\bTreatise\b|\bFederal Practice and Procedure\b|\bWright & Miller\b",  # treatise hints
        r"\[SRC:\s*DOC\d{4}\]",  # explicit source tags
    ]
    return any(re.search(p, content) for p in patterns)
