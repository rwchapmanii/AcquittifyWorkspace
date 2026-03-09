import streamlit as st


DARK_THEME_CSS = """
<style>
:root {
    color-scheme: light;
    --aq-bg: #f7f7f7;
    --aq-bg-soft: #efefef;
    --aq-bg-card: #ffffff;
    --aq-text-primary: #111111;
    --aq-text-secondary: #2b2b2b;
    --aq-text-muted: #5c5c5c;
    --primary-color: #111111;
    --background-color: #f7f7f7;
    --secondary-background-color: #efefef;
    --text-color: #111111;
    --aq-blue-400: #1f1f1f;
    --aq-blue-500: #111111;
    --aq-blue-600: #0b0b0b;
    --aq-border: #d9d9d9;
    --aq-radius: 12px;
    --aq-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    --aq-focus: #111111;
    --aq-danger: #111111;
    --aq-button-bg: #ffffff;
    --aq-button-bg-hover: #f2f2f2;
    --aq-button-bg-active: #e6e6e6;
    --aq-button-text: #111111;
    --aq-button-border: #cfcfcf;
}
html, body, [class*="css"] {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-weight: 400;
    letter-spacing: -0.01em;
    color: var(--aq-text-primary);
    font-size: 1rem;
    line-height: 1.6;
}
body, .stApp {
    background-color: var(--aq-bg);
}
a, a:visited {
    color: var(--aq-text-secondary);
}
a:hover {
    color: var(--aq-text-primary);
}
header { display: none; }
.block-container {
    max-width: 100% !important;
    padding-left: 2rem;
    padding-right: 2rem;
    padding-top: 2rem;
    padding-bottom: 2rem;
}
h1 { font-size: clamp(2rem, 4vw + 1rem, 2.25rem); font-weight: 700; margin-bottom: 0.8rem; color: var(--aq-text-primary); }
h2 { font-size: clamp(1.4rem, 3vw + 0.4rem, 1.7rem); font-weight: 600; margin-bottom: 0.6rem; color: var(--aq-text-primary); }
h3 { font-size: clamp(1.2rem, 2vw + 0.4rem, 1.6rem); font-weight: 500; margin-bottom: 0.5rem; }
p, li, label { font-size: 0.98rem; color: var(--aq-text-secondary); }
small { color: var(--aq-text-muted); }
textarea, input, .stTextInput input {
    background-color: var(--aq-bg-card);
    color: var(--aq-text-primary);
    border: 1px solid var(--aq-border);
    border-radius: var(--aq-radius);
    padding: 0.75rem;
    font-size: 0.95rem;
}
input[type="checkbox"],
input[type="radio"],
input[type="range"] {
    accent-color: var(--aq-button-bg);
}
textarea:focus, input:focus, textarea:focus-visible, input:focus-visible {
    outline: none;
    box-shadow: 0 0 0 2px rgba(17, 17, 17, 0.2);
}
[data-testid="stSelectbox"] div[data-baseweb="select"],
[data-testid="stMultiSelect"] div[data-baseweb="select"] {
    background-color: var(--aq-bg-card) !important;
    border-radius: var(--aq-radius);
    border: 1px solid var(--aq-border);
}
[data-testid="stSelectbox"] div[data-baseweb="select"] svg,
[data-testid="stMultiSelect"] div[data-baseweb="select"] svg {
    fill: var(--aq-text-muted) !important;
}
[data-testid="stSelectbox"] span,
[data-testid="stMultiSelect"] span,
[data-testid="stSelectbox"] div,
[data-testid="stMultiSelect"] div {
    color: var(--aq-text-primary) !important;
}

[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input {
    background-color: var(--aq-bg-card) !important;
    color: var(--aq-text-primary) !important;
    border: 1px solid var(--aq-border) !important;
    border-radius: var(--aq-radius) !important;
}

div[data-baseweb="popover"] ul,
div[data-baseweb="menu"] ul {
    background: var(--aq-bg-card) !important;
    color: var(--aq-text-primary) !important;
    border: 1px solid var(--aq-border) !important;
}
div[data-baseweb="popover"] li[role="option"],
div[data-baseweb="menu"] li[role="option"] {
    background: transparent !important;
    color: var(--aq-text-primary) !important;
}
div[data-baseweb="popover"] li[role="option"][aria-selected="true"],
div[data-baseweb="popover"] li[role="option"]:hover,
div[data-baseweb="menu"] li[role="option"][aria-selected="true"],
div[data-baseweb="menu"] li[role="option"]:hover {
    background: #f1f1f1 !important;
}
div[data-baseweb="tag"] {
    background: #f1f1f1 !important;
    color: var(--aq-text-primary) !important;
    border: 1px solid var(--aq-border) !important;
}
div[data-baseweb="tag"] svg {
    color: var(--aq-text-muted) !important;
    fill: var(--aq-text-muted) !important;
}

[data-testid="stFileUploaderDropzone"] {
    background: var(--aq-bg-card) !important;
    border: 1px dashed var(--aq-border) !important;
    color: var(--aq-text-secondary) !important;
    border-radius: var(--aq-radius) !important;
}

[data-testid="stExpander"] > div {
    background: var(--aq-bg-card) !important;
    border: 1px solid var(--aq-border) !important;
    border-radius: var(--aq-radius) !important;
}

[data-testid="stExpander"] summary {
    color: var(--aq-text-primary) !important;
}

[data-testid="stExpander"] summary:hover {
    background: #f3f3f3 !important;
}

[data-testid="stDataFrame"] div[role="grid"],
[data-testid="stDataFrame"] div[role="grid"] * {
    background: var(--aq-bg-card) !important;
    color: var(--aq-text-primary) !important;
}

div[data-testid="stAlert"] {
    background: #f3f3f3 !important;
    border: 1px solid var(--aq-border) !important;
    color: var(--aq-text-primary) !important;
    border-radius: var(--aq-radius) !important;
}
div[data-testid="stAlert"] svg {
    color: var(--aq-text-primary) !important;
    fill: var(--aq-text-primary) !important;
}

div[data-testid="stChatMessage"] {
    background: var(--aq-bg-card) !important;
    border: 1px solid var(--aq-border) !important;
    border-radius: var(--aq-radius) !important;
    padding: 0.75rem 0.9rem !important;
}

div[data-testid="stChatMessage"] * {
    color: var(--aq-text-primary) !important;
}

div[data-testid="stChatInput"] textarea {
    background: var(--aq-bg-card) !important;
    color: var(--aq-text-primary) !important;
    border: 1px solid var(--aq-border) !important;
    border-radius: var(--aq-radius) !important;
}
div[data-testid="stTabs"] button[role="tab"] {
    color: var(--aq-text-muted) !important;
}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: var(--aq-text-primary) !important;
    border-bottom: 2px solid var(--aq-text-primary) !important;
}
div[data-testid="stProgress"] div[role="progressbar"] {
    background: #e6e6e6 !important;
}
div[data-testid="stProgress"] div[role="progressbar"] > div {
    background: var(--aq-text-primary) !important;
}
div[data-testid="stSpinner"] svg {
    color: var(--aq-text-primary) !important;
    fill: var(--aq-text-primary) !important;
}
div[data-baseweb="toggle"] div[role="switch"] {
    background: #e0e0e0 !important;
}
div[data-baseweb="toggle"] div[role="switch"][aria-checked="true"] {
    background: var(--aq-button-bg) !important;
}
.stButton > button {
    all: unset;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--aq-button-bg);
    color: var(--aq-button-text);
    font-weight: 600;
    font-size: 0.95rem;
    padding: 0.65rem 1.4rem;
    border-radius: 10px;
    border: 1px solid var(--aq-button-border);
    cursor: pointer;
    transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.2s ease, border-color 0.2s ease;
    box-shadow: 0 8px 18px rgba(0, 0, 0, 0.15);
}
.stButton > button * {
    color: var(--aq-button-text) !important;
}
.stDownloadButton > button,
.stFormSubmitButton > button,
button[data-testid="baseButton-primary"],
button[data-testid="baseButton-secondary"],
button[data-testid="baseButton-secondaryFormSubmit"],
button[kind="primary"],
button[kind="secondary"] {
    background: var(--aq-button-bg) !important;
    color: var(--aq-button-text) !important;
    border: 1px solid var(--aq-button-border) !important;
    border-radius: 10px !important;
}
.stDownloadButton > button *,
.stFormSubmitButton > button *,
button[data-testid="baseButton-primary"] *,
button[data-testid="baseButton-secondary"] *,
button[data-testid="baseButton-secondaryFormSubmit"] *,
button[kind="primary"] *,
button[kind="secondary"] * {
    color: var(--aq-button-text) !important;
}
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover,
button[data-testid="baseButton-primary"]:hover,
button[data-testid="baseButton-secondary"]:hover,
button[data-testid="baseButton-secondaryFormSubmit"]:hover,
button[kind="primary"]:hover,
button[kind="secondary"]:hover {
    background: var(--aq-button-bg-hover) !important;
    border-color: #bdbdbd !important;
}
.stDownloadButton > button:active,
.stFormSubmitButton > button:active,
button[data-testid="baseButton-primary"]:active,
button[data-testid="baseButton-secondary"]:active,
button[data-testid="baseButton-secondaryFormSubmit"]:active,
button[kind="primary"]:active,
button[kind="secondary"]:active {
    background: var(--aq-button-bg-active) !important;
}
.stFileUploader button {
    background: var(--aq-button-bg) !important;
    color: var(--aq-button-text) !important;
    border: 1px solid var(--aq-button-border) !important;
    border-radius: 10px !important;
}
.stFileUploader button * {
    color: var(--aq-button-text) !important;
}
.stButton > button:hover {
    background: var(--aq-button-bg-hover);
    border-color: #bdbdbd;
    transform: translateY(-1px);
}
.stButton > button:active {
    background: var(--aq-button-bg-active);
    transform: translateY(0);
}
.stButton > button:disabled,
.stButton > button[disabled] {
    background: #ededed !important;
    color: #8a8a8a !important;
    border-color: #e0e0e0 !important;
    cursor: not-allowed !important;
    box-shadow: none !important;
}
.stButton > button.aq-button-start {
    background: var(--aq-button-bg) !important;
    color: var(--aq-button-text) !important;
    border-color: var(--aq-button-border) !important;
}
.stButton > button.aq-button-stop {
    background: #111111 !important;
    color: #ffffff !important;
    border-color: #111111 !important;
    box-shadow: none !important;
}
.stButton > button.aq-button-stop:hover {
    border-color: #000000 !important;
}
[data-testid="stExpander"] .stDownloadButton > button,
[data-testid="stExpander"] button[aria-label="Archive chat"],
[data-testid="stExpander"] button[aria-label="Delete chat"] {
    background: none !important;
    box-shadow: none !important;
    padding: 0.35rem 0 !important;
    margin: 0.15rem 0 !important;
    color: var(--aq-text-secondary) !important;
    text-align: left !important;
    width: 100% !important;
    font-size: 0.95rem !important;
    line-height: 1.4 !important;
    font-weight: 500 !important;
}
hr { border: none; height: 1px; background: var(--aq-border); margin: 1.5rem 0; }
section[data-testid="stSidebar"] { background-color: var(--aq-bg-soft); border-right: 1px solid var(--aq-border); }
section[data-testid="stSidebar"] * { color: var(--aq-text-secondary); }
.aq-brand-header { text-align: center; margin-top: 0; margin-bottom: 0.75rem; }
.aq-brand-header--left { text-align: left; padding: 16px; display: flex; align-items: center; gap: 12px; }
.aq-brand-logo-hero { width: 144px; height: auto; display: block; margin: 0 auto; }
.aq-brand-logo-icon { width: 104px; height: auto; display: block; margin: 0 auto; padding-top: 24px; }
.aq-brand-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    width: 100%;
    padding: 4px 0 16px 0;
    margin-bottom: 14px;
    border-bottom: 1px solid var(--aq-border);
}
.aq-brand-logo { width: 40px; height: auto; }
.aq-brand-wordmark { font-weight: 700; font-size: 1.6rem; letter-spacing: 0.01em; color: var(--aq-text-primary); }
.aq-brand-wordmark--center { text-align: center; }
.aq-case-title { text-align: left; }
.aq-case-title h2 { text-align: left; margin-top: 0.25rem; }
.aq-brand-divider { border-bottom: 1px solid var(--aq-border); margin: 12px 0 14px; }
.aq-topbar { display: none; }
.aq-alert {
    border-radius: var(--aq-radius);
    padding: 0.85rem 1rem;
    border: 1px solid var(--aq-border);
    background: #f5f5f5;
    color: var(--aq-text-secondary);
    margin: 0.5rem 0 1rem;
    box-shadow: var(--aq-shadow);
}
.aq-alert--error {
    border-left: 4px solid var(--aq-danger);
}
.aq-alert--error strong {
    color: var(--aq-danger);
}
.aq-mic-card {
    border: 1px solid var(--aq-border);
    background: var(--aq-bg-card);
    border-radius: 12px;
    padding: 12px;
    box-shadow: var(--aq-shadow);
}
.aq-mic-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.45rem 0.9rem;
    border-radius: 8px;
    border: 1px solid var(--aq-button-border);
    background: var(--aq-button-bg);
    color: var(--aq-button-text);
    font-weight: 600;
    font-size: 0.9rem;
    cursor: pointer;
    transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.2s ease, border-color 0.2s ease;
    box-shadow: 0 6px 14px rgba(0, 0, 0, 0.15);
}
.aq-mic-button:hover {
    background: var(--aq-button-bg-hover);
    border-color: #bdbdbd;
    transform: translateY(-1px);
}
.aq-mic-button:active {
    background: var(--aq-button-bg-active);
    transform: translateY(0);
}
.aq-mic-button:focus-visible {
    outline: 2px solid var(--aq-focus);
    outline-offset: 2px;
}
.aq-mic-row {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 8px;
}
.aq-mic-status {
    margin-top: 8px;
    font-size: 0.9rem;
    color: var(--aq-text-muted);
}
.aq-mic-stream-status {
    font-size: 0.9rem;
    color: var(--aq-text-muted);
}
.aq-status-active {
    color: var(--aq-text-primary);
    font-weight: 700;
}
.aq-status-muted {
    color: var(--aq-text-muted);
}
@media (max-width: 900px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    h1 { font-size: clamp(1.75rem, 4vw + 0.8rem, 2.2rem); }
    h2 { font-size: clamp(1.35rem, 3vw + 0.4rem, 1.8rem); }
    h3 { font-size: clamp(1.1rem, 2vw + 0.3rem, 1.4rem); }
}
</style>
"""


def inject_acquittify_brand():
    st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)
