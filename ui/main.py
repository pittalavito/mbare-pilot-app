"""Frontend entry point: ``streamlit run ui/main.py`` (resource/scripts/3-run-ui.py).
The UI only talks to the backend API (API_URL in .env): it never imports src/."""
import streamlit as st

from views.router import run_router

st.set_page_config(page_title="Mbare Pilot", page_icon="🧭", layout="wide")
run_router()
