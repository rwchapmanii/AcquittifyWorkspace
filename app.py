from __future__ import annotations

import streamlit as st

from acquittify_brand import LOGO_MARK
from brand import inject_acquittify_brand
from document_ingestion_ui import render_ingestion_page
from transcript_ingestion_ui import render_transcript_ingestion_page

BLUEBOOK_POLICY_TEXT = "Bluebook citation format is enforced when authoritative citations are available."


def main() -> None:
    st.set_page_config(
        page_title="Acquittify",
        layout="wide",
        page_icon=str(LOGO_MARK) if LOGO_MARK.exists() else None,
    )

    inject_acquittify_brand()
    st.title("Acquittify")
    st.caption("Case intelligence and ingestion workspace")
    st.caption(BLUEBOOK_POLICY_TEXT)

    tab_ingest, tab_transcript = st.tabs(["Case Record Ingestion", "Transcript Ingestion"])

    with tab_ingest:
        render_ingestion_page()

    with tab_transcript:
        case_name = st.session_state.get("case_name") or st.session_state.get("case_id")
        render_transcript_ingestion_page(case_name=case_name, show_title=False)


if __name__ == "__main__":
    main()
