import streamlit as st
import pandas as pd
import requests
from urllib.parse import quote

st.set_page_config(
    page_title="Peppol Endpoint Finder",
    layout="wide"
)

st.title("🔍 Peppol Endpoint Finder")

environment = st.radio(
    "Environment",
    ["PROD", "TEST"],
    horizontal=True
)

search_type = st.selectbox(
    "Search By",
    [
        "Customer Name",
        "VAT Number",
        "Participant ID / Org ID"
    ]
)

search_value = st.text_input(
    "Enter Search Value"
)

if environment == "PROD":
    base_url = "https://directory.peppol.eu/public/locale-en_US/menuitem-search"
else:
    base_url = "https://test-directory.peppol.eu/public/locale-en_US/menuitem-search"

if st.button("Search"):

    if search_value:

        encoded_value = quote(search_value)

        search_url = (
            f"{base_url}?q={encoded_value}&country="
        )

        st.subheader("Generated URL")

        st.code(search_url)

        st.write(search_url)

        try:

            response = requests.get(
                search_url,
                timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            st.subheader("Connection Test")

            st.success(
                f"Status Code: {response.status_code}"
            )

            st.write(
                f"Response Size: {len(response.text):,} characters"
            )

            with st.expander(
                "Show First 3000 Characters"
            ):
                st.text(response.text[:3000])

        except Exception as e:

            st.error(f"Error: {e}")

st.divider()

st.subheader("Bulk Upload")

uploaded_file = st.file_uploader(
    "Upload Excel or CSV",
    type=["xlsx", "csv"]
)

if uploaded_file:

    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.write("Preview")

    st.dataframe(df)

    if st.button("Generate Search Links"):

        results = []

        for _, row in df.iterrows():

            search_val = str(row.iloc[0]).strip()

            encoded_value = quote(search_val)

            search_url = (
                f"{base_url}?q={encoded_value}&country="
            )

            results.append({
                "Search Value": search_val,
                "Peppol URL": search_url
            })

        result_df = pd.DataFrame(results)

        st.dataframe(
            result_df,
            use_container_width=True
        )

        csv = result_df.to_csv(index=False)

        st.download_button(
            label="Download Results",
            data=csv,
            file_name="peppol_links.csv",
            mime="text/csv"
        )

st.divider()

if st.button("Test Peppol Connectivity"):

    try:

        response = requests.get(
            base_url,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        st.success(
            f"Connected Successfully ({response.status_code})"
        )

    except Exception as e:

        st.error(f"Connection failed: {e}")
