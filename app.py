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

search_value = st.text_input(
    "Customer Name / VAT / Participant ID"
)


def search_peppol(search_term, env):

    if env == "PROD":
        base_url = "https://directory.peppol.eu/search/1.0/json"
    else:
        base_url = "https://test-directory.peppol.eu/search/1.0/json"

    all_matches = []
    page = 0

    while True:

        url = (
            f"{base_url}?q={quote(search_term)}&page={page}"
        )

        response = requests.get(
            url,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        response.raise_for_status()

        data = response.json()

        matches = data.get("matches", [])

        if not matches:
            break

        all_matches.extend(matches)

        st.write(
            f"Loaded page {page + 1} ({len(matches)} results)"
        )

        # API returns 20 results per page
        if len(matches) < 20:
            break

        page += 1

    return all_matches


# ====================================
# SINGLE SEARCH
# ====================================

if st.button("Search"):

    if search_value:

        try:

            matches = search_peppol(
                search_value,
                environment
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
                    "Company Name": company_name,
                    "Participant ID": participant.get(
                        "value",
                        ""
                    ),
                    "Scheme": participant.get(
                        "scheme",
                        ""
                    ),
                    "Country": match.get(
                        "countryCode",
                        ""
                    ),
                    "Doc Type Count": len(
                        match.get(
                            "docTypes",
                            []
                        )
                    )
                })

            result_df = pd.DataFrame(results)

            st.success(
                f"{len(result_df)} result(s) found"
            )

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
                "peppol_results.csv",
                "text/csv"
            )

        except Exception as e:

            st.error(str(e))


# ====================================
# BULK SEARCH
# ====================================

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

    st.dataframe(df)

    if st.button("Lookup All"):

        all_results = []

        progress_bar = st.progress(0)

        total_rows = len(df)

        for index, row in df.iterrows():

            search_term = str(
                row.iloc[0]
            ).strip()

            try:

                matches = search_peppol(
                    search_term,
                    environment
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
                            "Search Value": search_term,
                            "Company Name": company_name,
                            "Participant ID": participant.get(
                                "value",
                                ""
                            ),
                            "Scheme": participant.get(
                                "scheme",
                                ""
                            ),
                            "Country": match.get(
                                "countryCode",
                                ""
                            ),
                            "Doc Type Count": len(
                                match.get(
                                    "docTypes",
                                    []
                                )
                            )
                        })

                else:

                    all_results.append({
                        "Search Value": search_term,
                        "Company Name": "NOT FOUND"
                    })

            except Exception as e:

                all_results.append({
                    "Search Value": search_term,
                    "Company Name": f"ERROR: {e}"
                })

            progress_bar.progress(
                (index + 1) / total_rows
            )

        results_df = pd.DataFrame(
            all_results
        )

        st.dataframe(
            results_df,
            use_container_width=True
        )

        csv = results_df.to_csv(
            index=False
        )

        st.download_button(
            "Download Bulk Results",
            csv,
            "peppol_bulk_results.csv",
            "text/csv"
        )
