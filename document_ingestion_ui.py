import streamlit as st
import importlib
import sys
import os
from pathlib import Path
from transcript_ingestion_ui import render_transcript_ingestion_page
from acquittify_brand import LOGO_MARK
from brand import inject_acquittify_brand
from case_manager import get_case_paths_by_id
from acquittify.local_workspace import resolve_data_root, resolve_workspace_id, workspace_root

SAMPLE_FACT_PATTERN = '''Perfect—here’s a **clean, realistic federal criminal defense fact pattern** that should stress-test Acquittify without turning into a law school hypo. It’s the kind of case where *intent, regulatory gray areas, and jury psychology* all matter.

---

## **Fact Pattern: United States v. Mercer**

### **Background**

Daniel Mercer is a **52-year-old licensed physician assistant** who operated a **pain management clinic** in suburban Ohio from 2016 to 2022. The clinic primarily treated **blue-collar patients** with chronic back, joint, and post-surgical pain. Mercer was not the clinic owner but served as its **medical director** and primary prescriber.

The clinic accepted **private insurance and Medicare**, and it employed two nurses and an office manager. Mercer had no prior criminal history and was respected in the community.

---

### **Investigation**

In 2021, the DEA initiated an investigation after receiving **anonymous complaints** alleging “pill mill” activity. The DEA conducted:

* **Undercover patient visits** (3 total)
* A **review of prescription data**, showing Mercer prescribed opioids at rates higher than the state average
* Interviews with **former patients**, some of whom later overdosed (non-fatal)

Agents executed a **search warrant** on the clinic and seized:

* Patient files
* Prescription logs
* Clinic policy manuals
* Mercer’s personal notes on patient pain assessments

No drugs, cash, or weapons were found.

---

### **Alleged Conduct**

The government alleges that Mercer:

1. **Prescribed oxycodone and hydromorphone outside the usual course of professional practice**
2. **Failed to adequately document medical necessity** in certain patient files
3. **Ignored red flags** such as early refill requests and positive drug screens for marijuana
4. **Delegated too much authority** to nurses in patient intake

The prosecution relies heavily on:

* **DEA expert testimony** regarding prescribing norms
* **Statistical comparisons** to other providers
* **Two former patients** who testify Mercer “didn’t really examine them”

---

### **Defense Facts**

The defense contends that:

* Mercer **personally examined every patient**
* Pain is **subjective and individualized**, not reducible to prescription averages
* Mercer attempted **dose reductions** and referred patients to physical therapy
* Clinic policies were **written with state board guidance**
* Undercover agents **misrepresented symptoms**
* Marijuana use was **not illegal under state law** at the time

Mercer received **no financial kickbacks**, no per-prescription bonuses, and was paid a **flat salary**.

---

### **Charges**

Mercer is charged with:

* **21 U.S.C. § 841(a)(1)** – Unlawful distribution of controlled substances
* **18 U.S.C. § 2** – Aiding and abetting
* **18 U.S.C. § 371** – Conspiracy (based on clinic operations)

---

### **Legal Questions to Test**

You can feed Acquittify prompts like:

* Whether the facts support criminal intent post-*Ruan*
* Rule 29 sufficiency issues
* Expert testimony admissibility under *Daubert*
* Jury instruction vulnerabilities
* Sentencing exposure if convicted
* Distinguishing malpractice from criminal liability
'''


DOCUMENT_TYPES = [
    "Transcript",
    "Court Record",
    "Witness Statement",
    "General Discovery",
    "Memorandum",
    "Case Law",
    "Other",
]


def _get_document_ingestion_backend():
    try:
        return importlib.import_module("document_ingestion_backend")
    except KeyError:
        sys.modules.pop("document_ingestion_backend", None)
        return importlib.import_module("document_ingestion_backend")


def render_ingestion_page() -> None:
    inject_acquittify_brand()

    st.title("Case Record Ingestion")

    st.markdown(
        "**Upload and ingest all case-related documents in a single unified workflow.**",
        unsafe_allow_html=True,
    )

    if st.session_state.get("sample_case"):
        st.markdown(st.session_state["sample_case"])

    if not st.session_state.get("case_id"):
        st.warning("Create or select a case first from the sidebar.")
        st.stop()

    configured_workspace = st.session_state.get("workspace_id") or os.getenv("ACQUITTIFY_WORKSPACE_ID") or "default"
    workspace_input = st.text_input(
        "Workspace ID",
        value=str(configured_workspace),
        key="case_record_workspace_id",
        help="All ingestion writes are scoped under this local workspace.",
    )
    workspace_id = resolve_workspace_id(workspace_input)
    st.session_state["workspace_id"] = workspace_id

    data_root = resolve_data_root(os.getenv("ACQUITTIFY_DATA_ROOT"), create=True)
    active_workspace_root = workspace_root(data_root=data_root, workspace_id=workspace_id, create=True)
    st.caption(f"Workspace: `{workspace_id}`  Data root: `{data_root}`")

    case_name = st.session_state.get("case_name") or st.session_state.get("case_id")
    case_paths = get_case_paths_by_id(
        st.session_state.get("case_id"),
        data_root=data_root,
        workspace_id=workspace_id,
    )
    st.caption(f"Case root: `{case_paths.root}`")

    doc_type = st.selectbox(
        "Document type (required)",
        options=["Select document type"] + DOCUMENT_TYPES,
        index=0,
        key="case_record_document_type",
    )

    if doc_type == "Select document type":
        st.markdown(
            "<div class=\"aq-alert aq-alert--error\"><strong>Action required:</strong> Select a document type to continue.</div>",
            unsafe_allow_html=True,
        )
        st.stop()

    if doc_type == "Transcript":
        st.info("Transcript ingestion uses the dedicated transcript pipeline.")
        render_transcript_ingestion_page(case_name=case_name, show_title=False)
        return

    uploads = st.file_uploader(
        "Upload case documents (PDF)",
        type=["pdf"],
        accept_multiple_files=True,
        key="case_record_uploads",
    )

    if uploads:
        too_large = []
        for upload in uploads:
            upload.seek(0, 2)
            file_size_mb = upload.tell() / (1024 * 1024)
            upload.seek(0)
            if file_size_mb > 50:
                too_large.append(upload.name)
        if too_large:
            st.warning(
                "The following files exceed 50MB and will be skipped: " + ", ".join(too_large),
                icon="⚠️",
            )

        if st.button("Ingest documents", key="case_record_ingest_btn"):
            st.write("Ingestion started...")
            dib = _get_document_ingestion_backend()
            results = dib.process_case_record_uploads(
                uploaded_files=uploads,
                case_name=case_name,
                case_root=case_paths.root,
                document_type=doc_type,
                data_root=data_root,
                workspace_id=workspace_id,
            )
            successes = [r for r in results if r.get("status") == "ingested"]
            failures = [r for r in results if r.get("status") != "ingested"]
            if successes:
                st.success(f"Ingested {len(successes)} document(s).")
                st.cache_data.clear()
            if failures:
                for failure in failures:
                    st.error(f"{failure.get('filename')}: {failure.get('message', 'Unknown error')}")
    else:
        st.info("Upload one or more PDF documents to begin.")

    st.markdown("---")
    st.subheader("Ingest local folder (PDFs)")
    st.caption("Use this for local folders on disk; it does not upload from the browser.")
    folder_path = st.text_input(
        "Folder path",
        key="case_record_folder_path",
        placeholder="/Users/you/Downloads/CaseFolder",
    )
    if st.button("Ingest folder", key="case_record_ingest_folder_btn"):
        if not folder_path.strip():
            st.error("Enter a folder path.")
        else:
            folder = Path(folder_path.strip()).expanduser()
            if not folder.exists() or not folder.is_dir():
                st.error("Folder not found.")
            else:
                pdf_paths = sorted(folder.rglob("*.pdf"))
                if not pdf_paths:
                    st.error("No PDF files found in the folder.")
                else:
                    st.write(f"Found {len(pdf_paths)} PDF(s). Ingestion started...")
                    dib = _get_document_ingestion_backend()
                    results = dib.process_case_record_paths(
                        pdf_paths=pdf_paths,
                        case_name=case_name,
                        case_root=case_paths.root,
                        document_type=doc_type,
                        data_root=data_root,
                        workspace_id=workspace_id,
                    )
                    successes = [r for r in results if r.get("status") == "ingested"]
                    failures = [r for r in results if r.get("status") != "ingested"]
                    if successes:
                        st.success(f"Ingested {len(successes)} document(s).")
                        st.cache_data.clear()
                    if failures:
                        for failure in failures:
                            st.error(f"{failure.get('filename')}: {failure.get('message', 'Unknown error')}")

    st.markdown("---")
    st.subheader("Drag & drop a folder (ZIP of PDFs)")
    st.caption("Compress a folder into a .zip, then drag and drop here.")
    zip_uploads = st.file_uploader(
        "Upload ZIP file(s)",
        type=["zip"],
        accept_multiple_files=True,
        key="case_record_zip_uploads",
    )
    if zip_uploads and st.button("Ingest ZIP file(s)", key="case_record_ingest_zip_btn"):
        dib = _get_document_ingestion_backend()
        all_results = []
        for zip_file in zip_uploads:
            results = dib.process_case_record_zip(
                uploaded_file=zip_file,
                case_name=case_name,
                case_root=case_paths.root,
                document_type=doc_type,
                data_root=data_root,
                workspace_id=workspace_id,
            )
            all_results.extend(results)
        successes = [r for r in all_results if r.get("status") == "ingested"]
        failures = [r for r in all_results if r.get("status") != "ingested"]
        if successes:
            st.success(f"Ingested {len(successes)} document(s) from ZIP.")
            st.cache_data.clear()
        if failures:
            for failure in failures:
                st.error(f"{failure.get('filename')}: {failure.get('message', 'Unknown error')}")


if __name__ == "__main__":
    st.set_page_config(
        page_title="Acquittify Upload",
        layout="wide",
        page_icon=str(LOGO_MARK) if LOGO_MARK.exists() else None
    )
    render_ingestion_page()
