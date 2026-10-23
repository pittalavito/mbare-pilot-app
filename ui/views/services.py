"""What every view needs: the UI config and the API client (one per Streamlit
server process)."""
import streamlit as st

from api_client.client import Api
from ui_config import UiConfig


@st.cache_resource
def config() -> UiConfig:
    return UiConfig()  # pyright: ignore[reportCallIssue]


@st.cache_resource
def api() -> Api:
    return Api(config().api_url)
