import os

from scripts.intent_service import classify


def _run(text: str) -> dict:
    dsn = os.getenv("COURTLISTENER_DB_DSN") or os.getenv("INTENT_DB_DSN")
    return classify(text, "2026.01", dsn)


def test_intent_regression_cases():
    cases = [
        ("404(b) notice / prior bad acts", "EVID.R404B."),
        ("unfair prejudice / 403", "EVID.R403."),
        ("jury instruction omitted / theory of defense instruction", "TRIAL.JURY.INSTR."),
        ("role enhancement / guideline calculation", "SENT.GUIDE."),
        ("motion to suppress", "4A."),
    ]
    for text, prefix in cases:
        result = _run(text)
        assert result["primary"]["code"].startswith(prefix)
