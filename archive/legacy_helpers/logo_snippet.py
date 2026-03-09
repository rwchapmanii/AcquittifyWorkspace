import streamlit as st
from pathlib import Path

# Set page config with new logo
st.set_page_config(
    page_title="Acquittify Upload",
    layout="wide",
    page_icon="/Users/ronaldchapman/Desktop/Acquittify/Acquittify Storage/Brading/Modern six-pointed abstract logo.png"
)

# Display logo in UI
st.image(
    "/Users/ronaldchapman/Desktop/Acquittify/Acquittify Storage/Brading/Modern six-pointed abstract logo.png",
    width=120,
    caption="Acquittify"
)

# ...existing code...
