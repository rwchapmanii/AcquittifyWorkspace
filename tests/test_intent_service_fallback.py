import psycopg

from scripts import intent_service


def test_classify_falls_back_to_file_taxonomy_when_db_unavailable(monkeypatch):
    def _raise_connect(*_args, **_kwargs):
        raise psycopg.OperationalError("db unavailable in test")

    monkeypatch.setattr(intent_service.psycopg, "connect", _raise_connect)
    intent_service._UNAVAILABLE_DSN.clear()

    result = intent_service.classify(
        "motion to suppress",
        version_override="2026.01",
        dsn_override="postgresql://localhost:5432/courtlistener",
    )

    assert result["primary"]["version"] == "2026.01"
    assert result["primary"]["code"] == "4A.SUPP.GEN.GEN"
