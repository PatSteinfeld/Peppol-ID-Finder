import streamlit as st
import pandas as pd

st.set_page_config(page_title="Peppol Endpoint Finder")

st.title("🔍 Peppol Endpoint Finder")

environment = st.radio(
    "Environment",
    ["PROD", "TEST"]
)

customer_name = st.text_input("Customer Name")

if st.button("Search"):
    st.success(
        f"Searching for '{customer_name}' in {environment}"
    )

uploaded_file = st.file_uploader(
    "Upload Excel",
    type=["xlsx", "csv"]
)

if uploaded_file:

    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.write("Preview")

    st.dataframe(df)
