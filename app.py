import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup

st.set_page_config(page_title="Peppol Endpoint Finder")

st.title("🔍 Peppol Endpoint Finder")

environment = st.radio(
    "Environment",
    ["PROD", "TEST"]
)

customer_name = st.text_input("Customer Name")


def search_peppol(customer, env):

    if env == "PROD":
        url = (
            "https://directory.peppol.eu/public/locale-en_US/"
            f"menuitem-search?q={customer}&country="
        )
    else:
        url = (
            "https://test-directory.peppol.eu/public/locale-en_US/"
            f"menuitem-search?q={customer}&country="
        )

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=20
    )

    return response.text


if st.button("Search"):

    with st.spinner("Searching PEPPOL..."):

        html = search_peppol(
            customer_name,
            environment
        )

        st.success("Search completed")

        st.text_area(
            "Returned HTML (first 5000 chars)",
            html[:5000],
            height=400
        )
