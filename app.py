import streamlit as st
import pandas as pd
import requests
from urllib.parse import quote

st.set_page_config(
    page_title="Peppol Endpoint Finder",
    layout="wide"
)

st.title("🔍 Peppol Endpoint Finder")

# =====================================================
# SETTINGS
# =====================================================

environment = st.radio(
    "Environment",
    ["PROD", "TEST"],
    horizontal=True
)

search_value = st.text_input(
    "Customer Name / VAT / Participant ID"
)

# =====================================================
# API FUNCTION
# =====================================================

def search_peppol(search_term, env):

    if env == "PROD":
        url = (
            f"https://directory.peppol.eu/search/1.0/json"
            f"?q={quote(search_term)}"
            f"&rpc=1000"
        )
    else:
        url = (
            f"https://test-directory.peppol.eu/search/1.0/json"
            f"?q={quote(search_term)}"
            f"&rpc=1000"
        )

    response = requests.get(
        url,
        timeout=60,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    return response.json()

# =====================================================
# SINGLE SEARCH
# =====================================================

if st.button("Search"):

    if search_value:

        try:

            data = search_peppol(
                search_value,
                environment
            )

            st.success(
                f"Total Results Found: "
                f"{data.get('total-result-count', 0)}"
            )

            st.info(
                f"Returned By API: "
                f"{data.get('used-result-count', 0)}"
            )

            matches = data.get(
                "matches",
                []
            )

            results = []

            for match in matches:

                participant = match.get(
                    "participantID",
                    {}
                )

                company_name = ""

                entities = match.get(
                    "entities",
                    []
                )

                if entities:

                    names = entities[0].get(
                        "name",
                        []
                    )

                    if names:

                        company_name = names[0].get(
                            "name",
                            ""
                        )

                results.append({

                    "Company Name":
                        company_name,

                    "Participant ID":
                        participant.get(
                            "value",
                            ""
                        ),

                    "Scheme":
                        participant.get(
                            "scheme",
                            ""
                        ),

                    "Country":
                        match.get(
                            "countryCode",
                            ""
                        ),

                    "Document Types":
                        len(
                            match.get(
                                "docTypes",
                                []
                            )
                        )

                })

            result_df = pd.DataFrame(results)

            st.dataframe(
                result_df,
                use_container_width=True,
                height=600
            )

            csv = result_df.to_csv(
                index=False
            )

            st.download_button(
                "⬇ Download Results",
                csv,
                "peppol_results.csv",
                "text/csv"
            )

        except Exception as e:

            st.error(
                f"Error: {str(e)}"
            )

# =====================================================
# BULK SEARCH
# =====================================================

st.divider()

st.subheader("Bulk Search")

uploaded_file = st.file_uploader(
    "Upload Excel or CSV",
    type=["xlsx", "csv"]
)

if uploaded_file:

    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.write("Input Preview")

    st.dataframe(df)

    if st.button("Lookup All"):

        all_results = []

        progress = st.progress(0)

        total_rows = len(df)

        for index, row in df.iterrows():

            search_term = str(
                row.iloc[0]
            ).strip()

            try:

                data = search_peppol(
                    search_term,
                    environment
                )

                matches = data.get(
                    "matches",
                    []
                )

                if matches:

                    for match in matches:

                        participant = match.get(
                            "participantID",
                            {}
                        )

                        company_name = ""

                        entities = match.get(
                            "entities",
                            []
                        )

                        if entities:

                            names = entities[0].get(
                                "name",
                                []
                            )

                            if names:

                                company_name = names[0].get(
                                    "name",
                                    ""
                                )

                        all_results.append({

                            "Search Value":
                                search_term,

                            "Company Name":
                                company_name,

                            "Participant ID":
                                participant.get(
                                    "value",
                                    ""
                                ),

                            "Scheme":
                                participant.get(
                                    "scheme",
                                    ""
                                ),

                            "Country":
                                match.get(
                                    "countryCode",
                                    ""
                                ),

                            "Document Types":
                                len(
                                    match.get(
                                        "docTypes",
                                        []
                                    )
                                )

                        })

                else:

                    all_results.append({

                        "Search Value":
                            search_term,

                        "Company Name":
                            "NOT FOUND",

                        "Participant ID":
                            "",

                        "Scheme":
                            "",

                        "Country":
                            "",

                        "Document Types":
                            ""

                    })

            except Exception as e:

                all_results.append({

                    "Search Value":
                        search_term,

                    "Company Name":
                        f"ERROR: {str(e)}",

                    "Participant ID":
                        "",

                    "Scheme":
                        "",

                    "Country":
                        "",

                    "Document Types":
                        ""

                })

            progress.progress(
                (index + 1) / total_rows
            )

        results_df = pd.DataFrame(
            all_results
        )

        st.success(
            f"{len(results_df)} rows returned"
        )

        st.dataframe(
            results_df,
            use_container_width=True,
            height=600
        )

        csv = results_df.to_csv(
            index=False
        )

        st.download_button(
            "⬇ Download Bulk Results",
            csv,
            "peppol_bulk_results.csv",
            "text/csv"
        )
