import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

st.set_page_config(
    page_title="Peppol Endpoint Finder",
    layout="wide"
)

st.title("🔍 Peppol Endpoint Finder")

# --------------------------
# FUNCTIONS
# --------------------------

def extract_links(html):
    soup = BeautifulSoup(html, "html.parser")

    results = []

    for link in soup.find_all("a", href=True):

        text = link.get_text(strip=True)

        href = link["href"]

        results.append({
            "Text": text,
            "Link": href
        })

    return results


def test_search(search_value, environment):

    if environment == "PROD":
        base_url = (
            "https://directory.peppol.eu/public/locale-en_US/menuitem-search"
        )
    else:
        base_url = (
            "https://test-directory.peppol.eu/public/locale-en_US/menuitem-search"
        )

    encoded_value = quote(search_value)

    search_url = (
        f"{base_url}?q={encoded_value}&country="
    )

    response = requests.get(
        search_url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    return search_url, response


# --------------------------
# SEARCH SECTION
# --------------------------

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

if st.button("Search"):

    if not search_value:
        st.warning("Please enter a value.")
    else:

        try:

            search_url, response = test_search(
                search_value,
                environment
            )

            st.subheader("Generated URL")

            st.code(search_url)

            st.markdown(search_url)

            st.subheader("Connection Test")

            st.success(
                f"Status Code: {response.status_code}"
            )

            st.write(
                f"Response Size: {len(response.text):,} characters"
            )

            links = extract_links(response.text)

            st.subheader("Links Found")

            st.write(
                f"Total Links Found: {len(links)}"
            )

            if len(links) > 0:

                st.dataframe(
                    pd.DataFrame(links),
                    use_container_width=True
                )

            with st.expander("Show First 3000 Characters"):

                st.text(
                    response.text[:3000]
                )

        except Exception as e:

            st.error(
                f"Error: {str(e)}"
            )

# --------------------------
# BULK UPLOAD
# --------------------------

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

        if environment == "PROD":
            base_url = (
                "https://directory.peppol.eu/public/locale-en_US/menuitem-search"
            )
        else:
            base_url = (
                "https://test-directory.peppol.eu/public/locale-en_US/menuitem-search"
            )

        results = []

        for _, row in df.iterrows():

            value = str(
                row.iloc[0]
            ).strip()

            encoded_value = quote(value)

            results.append(
                {
                    "Search Value": value,
                    "Search URL": (
                        f"{base_url}?q={encoded_value}&country="
                    )
                }
            )

        result_df = pd.DataFrame(results)

        st.dataframe(
            result_df,
            use_container_width=True
        )

        csv = result_df.to_csv(
            index=False
        )

        st.download_button(
            "Download Results",
            csv,
            "peppol_search_links.csv",
            "text/csv"
        )

# --------------------------
# CONNECTIVITY TEST
# --------------------------

st.divider()

if st.button("Test Peppol Connectivity"):

    try:

        if environment == "PROD":
            url = (
                "https://directory.peppol.eu/public/locale-en_US/menuitem-search"
            )
        else:
            url = (
                "https://test-directory.peppol.eu/public/locale-en_US/menuitem-search"
            )

        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        st.success(
            f"Connected Successfully ({response.status_code})"
        )

    except Exception as e:

        st.error(
            f"Connection Failed: {str(e)}"
        )
