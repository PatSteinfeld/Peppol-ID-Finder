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


def get_api_url(search_term, env):
    search_term = quote(search_term)

    if env == "PROD":
        return (
            f"https://directory.peppol.eu/"
            f"search/1.0/json?q={search_term}"
        )

    return (
        f"https://test-directory.peppol.eu/"
        f"search/1.0/json?q={search_term}"
    )


def search_peppol(search_term, env):

    url = get_api_url(search_term, env)

    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    return response.json()


# ------------------------
# SINGLE SEARCH
# ------------------------

if st.button("Search"):

    if search_value:

        try:

            data = search_peppol(
                search_value,
                environment
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

                entities = match.get(
                    "entities",
                    []
                )

                entity_name = ""

                if entities:
                    names = entities[0].get(
                        "name",
                        []
                    )

                    if names:
                        entity_name = names[0].get(
                            "name",
                            ""
                        )

                results.append({

                    "Company Name":
                        entity_name,

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

                    "Doc Type Count":
                        len(
                            match.get(
                                "docTypes",
                                []
                            )
                        )

                })

            result_df = pd.DataFrame(
                results
            )

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


# ------------------------
# BULK SEARCH
# ------------------------

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

        progress = st.progress(0)

        total = len(df)

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

                        entities = match.get(
                            "entities",
                            []
                        )

                        entity_name = ""

                        if entities:
                            names = entities[0].get(
                                "name",
                                []
                            )

                            if names:
                                entity_name = names[0].get(
                                    "name",
                                    ""
                                )

                        all_results.append({

                            "Search Value":
                                search_term,

                            "Company Name":
                                entity_name,

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
                            ""

                    })

            except Exception:

                all_results.append({

                    "Search Value":
                        search_term,

                    "Company Name":
                        "ERROR",

                    "Participant ID":
                        "",

                    "Scheme":
                        "",

                    "Country":
                        ""

                })

            progress.progress(
                (index + 1) / total
            )

        result_df = pd.DataFrame(
            all_results
        )

        st.dataframe(
            result_df,
            use_container_width=True
        )

        csv = result_df.to_csv(
            index=False
        )

        st.download_button(
            "Download Excel Results",
            csv,
            "peppol_bulk_results.csv",
            "text/csv"
        )
