from pathlib import Path


def test_sentencing_calculator_asset_exists() -> None:
    project_root = Path(__file__).resolve().parents[1]
    calculator_path = project_root / "assets" / "sentencing_guidelines" / "calculator.html"
    assert calculator_path.exists()
    content = calculator_path.read_text(encoding="utf-8")
    assert "Sentencing Guidelines" in content
