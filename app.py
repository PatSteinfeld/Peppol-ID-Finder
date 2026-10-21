import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
import streamlit as st

# =====================================================
# CONFIG
# =====================================================

BASE_URL = {
    "PROD": "https://directory.peppol.eu",
    "TEST": "https://test-directory.peppol.eu",
}
HEADERS = {"User-Agent": "PeppolEndpointFinder/1.0 (contact: you@example.com)"}
PAGE_SIZE = 1000   # results per API call
MAX_PAGES = 5      # safety cap per search term
MAX_WORKERS = 4    # keep modest: this is a public service

st.set_page_config(page_title="Peppol Endpoint Finder", layout="wide")
st.title("🔍 Peppol Endpoint Finder")

# =====================================================
# API
# =====================================================


def fetch_all(term: str, env: str) -> dict:
    """Fetch all pages for a search term (up to MAX_PAGES). Thread-safe, no Streamlit calls."""
    matches, begin, total = [], 0, 0
    for _ in range(MAX_PAGES):
        r = requests.get(
            f"{BASE_URL[env]}/search/1.0/json",
            params={"q": term, "rpc": PAGE_SIZE, "beginIndex": begin},
            headers=HEADERS,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        total = data.get("total-result-count", 0)
        page = data.get("matches", [])
        matches += page
        begin += len(page)
        if not page or begin >= total:
            break
    return {"total": total, "matches": matches}


@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(term: str, env: str) -> dict:
    return fetch_all(term, env)


# =====================================================
# PARSING
# =====================================================


def norm(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(s)).upper()


def classify(term: str, pid: str, identifiers: list[str], names: list[str]) -> int:
    """Heuristic match rank: 0 = ID/VAT, 1 = exact name, 2 = name contains, 3 = fuzzy."""
    t = norm(term)
    t_no_cc = t[2:] if len(t) > 2 and t[:2].isalpha() else t  # strip VAT country prefix
    candidates = [norm(pid)] + [norm(i) for i in identifiers]
    for c in candidates:
        if t and (t == c or (len(t) >= 6 and t in c) or (len(t_no_cc) >= 6 and t_no_cc in c)):
            return 0
    tl = term.casefold().strip()
    if any(tl == n.casefold() for n in names):
        return 1
    if tl and any(tl in n.casefold() for n in names):
        return 2
    return 3


RANK_LABEL = {0: "ID / VAT match", 1: "Exact name", 2: "Name contains", 3: "Fuzzy"}


def parse_matches(matches: list, term: str | None = None) -> list[dict]:
    rows = []
    for m in matches:
        pid = m.get("participantID", {})
        entities = m.get("entities") or [{}]
        names = [n.get("name", "") for e in entities for n in e.get("name", []) if n.get("name")]
        identifiers = [
            i.get("value", "") for e in entities for i in e.get("identifiers", []) if i.get("value")
        ]
        countries = sorted({e.get("countryCode", "") for e in entities if e.get("countryCode")})
        doc_types = m.get("docTypes", [])
        accepts_invoice = any(
            "Invoice-2::Invoice" in d.get("value", "") and "en16931" in d.get("value", "")
            for d in doc_types
        )
        row = {
            "Company Name": "; ".join(dict.fromkeys(names)),
            "Participant ID": pid.get("value", ""),
            "Scheme": pid.get("scheme", ""),
            "Country": ", ".join(countries) or m.get("countryCode", ""),
            "Identifiers": "; ".join(dict.fromkeys(identifiers)),
            "Document Types": len(doc_types),
            "Accepts Invoice (BIS 3)": "Yes" if accepts_invoice else "No",
        }
        if term is not None:
            rank = classify(term, pid.get("value", ""), identifiers, names)
            row = {"Search Value": term, "Match Type": RANK_LABEL[rank], "_rank": rank, **row}
        rows.append(row)
    return rows


def mark_best(df: pd.DataFrame) -> pd.DataFrame:
    """Add a Best Match flag: rows with the best rank per search value (if better than fuzzy)."""
    if df.empty or "_rank" not in df:
        return df
    best = df.groupby("Search Value")["_rank"].transform("min")
    df["Best Match"] = ((df["_rank"] == best) & (df["_rank"] < 3)).map({True: "✔", False: ""})
    df = df.sort_values(["Search Value", "_rank"], kind="stable")
    return df.drop(columns="_rank")


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """UTF-8 with BOM (Excel-friendly) and neutralised formula-injection prefixes."""
    safe = df.copy()
    for col in safe.select_dtypes(include="object").columns:
        safe[col] = safe[col].map(
            lambda v: "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v
        )
    return safe.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


# =====================================================
# SETTINGS
# =====================================================

environment = st.radio("Environment", ["PROD", "TEST"], horizontal=True)

# =====================================================
# SINGLE SEARCH
# =====================================================

with st.form("single_search"):
    search_value = st.text_input("Customer Name / VAT / Participant ID")
    submitted = st.form_submit_button("Search")

if submitted and search_value.strip():
    term = search_value.strip()
    try:
        with st.spinner("Searching..."):
            data = cached_search(term, environment)
        rows = parse_matches(data["matches"], term)
        df = mark_best(pd.DataFrame(rows)) if rows else pd.DataFrame()
        st.session_state["single"] = {
            "df": df,
            "total": data["total"],
            "fetched": len(data["matches"]),
            "term": term,
        }
    except requests.RequestException as e:
        st.session_state.pop("single", None)
        st.error(f"Network/API error: {e}")
    except Exception as e:
        st.session_state.pop("single", None)
        st.error(f"Unexpected error: {e}")

single = st.session_state.get("single")
if single:
    st.success(f"Total results for '{single['term']}': {single['total']}")
    if single["fetched"] < single["total"]:
        st.warning(
            f"Only {single['fetched']} of {single['total']} results were fetched "
            f"(page cap reached). Refine your search."
        )
    if single["df"].empty:
        st.info("No matches found.")
    else:
        st.dataframe(single["df"], width="stretch", height=600)
        st.download_button(
            "⬇ Download Results",
            to_csv_bytes(single["df"]),
            "peppol_results.csv",
            "text/csv",
        )

# =====================================================
# BULK SEARCH
# =====================================================

st.divider()
st.subheader("Bulk Search")

uploaded = st.file_uploader("Upload Excel or CSV", type=["xlsx", "csv"])

if uploaded:
    has_header = st.checkbox("First row is a header", value=True)
    header = 0 if has_header else None
    try:
        if uploaded.name.lower().endswith(".csv"):
            # dtype=str keeps leading zeros in VAT / IDs; keep_default_na=False avoids "nan" strings
            in_df = pd.read_csv(uploaded, header=header, dtype=str, keep_default_na=False)
        else:
            in_df = pd.read_excel(uploaded, header=header, dtype=str).fillna("")
    except Exception as e:
        st.error(f"Could not read file: {e}")
        st.stop()

    in_df.columns = [str(c) for c in in_df.columns]
    column = st.selectbox("Column to search", in_df.columns, index=0)

    # Clean, de-duplicate (order preserved), drop blanks
    raw_terms = [str(v).strip() for v in in_df[column]]
    terms = list(dict.fromkeys(t for t in raw_terms if t and t.lower() != "nan"))

    st.write(
        f"Input preview ({len(raw_terms)} rows, {len(terms)} unique non-empty values to look up)"
    )
    st.dataframe(in_df.head(50), width="stretch")

    if st.button("Lookup All") and terms:
        results, progress = [], st.progress(0.0, text="Starting...")

        def work(t: str):
            try:
                data = fetch_all(t, environment)
                found = parse_matches(data["matches"], t)
                trunc = len(data["matches"]) < data["total"]
                if not found:
                    return [{"Search Value": t, "Status": "NOT FOUND"}]
                for r in found:
                    r["Status"] = "OK (truncated)" if trunc else "OK"
                return found
            except requests.RequestException as e:
                return [{"Search Value": t, "Status": f"ERROR: {e}"}]
            except Exception as e:
                return [{"Search Value": t, "Status": f"ERROR (parsing): {e}"}]

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(work, t) for t in terms]
            for done, fut in enumerate(as_completed(futures), start=1):
                results.extend(fut.result())
                progress.progress(done / len(terms), text=f"{done}/{len(terms)} looked up")

        out = pd.DataFrame(results)
        if "_rank" in out:
            ranked = mark_best(out[out["_rank"].notna()].copy())
            unranked = out[out["_rank"].isna()].drop(columns="_rank")
            out = pd.concat([ranked, unranked], ignore_index=True)
        out = out.drop_duplicates(subset=["Search Value", "Participant ID"], keep="first") \
            if "Participant ID" in out else out

        # Put key columns first, keep original input order for search values
        order = {t: i for i, t in enumerate(terms)}
        out = out.sort_values("Search Value", key=lambda s: s.map(order), kind="stable")
        first_cols = ["Search Value", "Status", "Best Match", "Match Type"]
        out = out[[c for c in first_cols if c in out] + [c for c in out if c not in first_cols]]
        out = out.fillna("")

        st.session_state["bulk"] = {
            "df": out,
            "n_terms": len(terms),
            "n_not_found": int((out["Status"] == "NOT FOUND").sum()),
            "n_errors": int(out["Status"].astype(str).str.startswith("ERROR").sum()),
        }

bulk = st.session_state.get("bulk")
if bulk:
    st.success(
        f"{len(bulk['df'])} rows for {bulk['n_terms']} searches "
        f"({bulk['n_not_found']} not found, {bulk['n_errors']} errors)"
    )
    st.dataframe(bulk["df"], width="stretch", height=600)
    st.download_button(
        "⬇ Download Bulk Results",
        to_csv_bytes(bulk["df"]),
        "peppol_bulk_results.csv",
        "text/csv",
    )
