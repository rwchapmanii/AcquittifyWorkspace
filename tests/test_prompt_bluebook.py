from pathlib import Path


def test_system_prompt_mentions_bluebook() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    text = app_path.read_text(encoding="utf-8")
    assert "Bluebook" in text
