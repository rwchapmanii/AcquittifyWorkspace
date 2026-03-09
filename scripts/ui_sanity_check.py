"""Simple UI sanity check for Streamlit branding CSS."""
from pathlib import Path


REQUIRED_SNIPPETS = [
    "stFileUploaderDropzone",
    "stTextArea",
    "stTextInput",
    "stExpander",
    "stAlert",
    "stChatMessage",
    "stChatInput",
]


def main() -> None:
    brand_path = Path(__file__).resolve().parents[1] / "brand.py"
    css = brand_path.read_text(encoding="utf-8")
    missing = [snippet for snippet in REQUIRED_SNIPPETS if snippet not in css]
    if missing:
        raise SystemExit(f"Missing CSS selectors in brand.py: {', '.join(missing)}")
    print("UI sanity check passed: required selectors found in brand.py")


if __name__ == "__main__":
    main()
