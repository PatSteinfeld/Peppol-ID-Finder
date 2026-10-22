import math
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =====================================================
# CONFIG
# =====================================================

BASE_URL = {
    "PROD": "https://directory.peppol.eu",
    "TEST": "https://test-directory.peppol.eu",
}
HEADERS = {"User-Agent": "PeppolEndpointFinder/1.0 (contact: you@example.com)"}
TIMEOUT = (5, 25)        # (connect, read) seconds - a hung request can no longer stall a run
CACHE_LIMIT = 5000       # max cached search terms

st.set_page_config(page_title="Peppol Endpoint Finder", layout="wide")
st.title("🔍 Peppol Endpoint Finder")

# =====================================================
# HTTP: per-thread session with connection reuse + retries
# =====================================================

_local = threading.local()


def get_session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        s.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=2))
        s.headers.update(HEADERS)
        _local.session = s
    return s


@st.cache_resource
def get_cache() -> dict:
    """Survives reruns, so a restarted bulk run skips terms that were already looked up."""
    return {"data": {}, "lock": threading.Lock()}


# =====================================================
# QUERY BUILDING (use the most selective API parameter available)
# =====================================================


def looks_like_id(term: str) -> bool:
    alnum = re.sub(r"[^0-9A-Za-z]", "", term)
    digits = sum(c.isdigit() for c in alnum)
    return len(alnum) >= 6 and digits >= 6 and digits / len(alnum) >= 0.6


def build_params(term: str, country: str) -> dict:
    t = term.strip()
    if re.fullmatch(r"\d{4}:\S+", t):                      # full participant ID -> exact lookup
        return {"participant": f"iso6523-actorid-upis::{t.lower()}"}
    if looks_like_id(t):                                   # VAT / enterprise number
        params = {"q": re.sub(r"[^0-9A-Za-z]", "", t)}
    elif len(t) >= 3:                                      # company name -> name-only match
        params = {"name": t}
    else:
        params = {"q": t}
    if country:
        params["country"] = country
    return params


def fetch_page(params: dict, env: str, page: int, size: int) -> dict:
    r = get_session().get(
        f"{BASE_URL[env]}/search/1.0/json",
        params={**params, "resultPageIndex": page, "resultPageCount": size},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def run_query(params: dict, env: str, size: int, max_pages: int) -> tuple[list, int]:
    matches, total = [], 0
    for page in range(max_pages):
        data = fetch_page(params, env, page, size)
        total = data.get("total-result-count", 0)
        got = data.get("matches", [])
        matches += got
        if not got or len(matches) >= total:
            break
    return matches, total


def fetch_term(term: str, env: str, country: str, size: int, max_pages: int) -> dict:
    params = build_params(term, country)
    matches, total = run_query(params, env, size, max_pages)
    if not matches and "name" in params:                   # fall back to the broader general query
        fallback = {"q": term.strip(), **({"country": country} if country else {})}
        matches, total = run_query(fallback, env, size, max_pages)
    return {"total": total, "matches": matches}


def lookup(term: str, env: str, country: str, size: int, max_pages: int, cache: dict) -> dict:
    key = (term.casefold(), env, country, size, max_pages)
    with cache["lock"]:
        hit = cache["data"].get(key)
    if hit is not None:
        return hit
    res = fetch_term(term, env, country, size, max_pages)
    with cache["lock"]:
        if len(cache["data"]) >= CACHE_LIMIT:
            cache["data"].clear()
        cache["data"][key] = res
    return res


# =====================================================
# PARSING
# =====================================================


def norm(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(s)).upper()


def classify(term: str, pid: str, identifiers: list[str], names: list[str]) -> int:
    """Heuristic match rank: 0 = ID/VAT, 1 = exact name, 2 = name contains, 3 = fuzzy."""
    t = norm(term)
    t_no_cc = t[2:] if len(t) > 2 and t[:2].isalpha() else t
    for c in [norm(pid)] + [norm(i) for i in identifiers]:
        if t and (t == c or (len(t) >= 6 and t in c) or (len(t_no_cc) >= 6 and t_no_cc in c)):
            return 0
    tl = term.casefold().strip()
    if any(tl == n.casefold() for n in names):
        return 1
    if tl and any(tl in n.casefold() for n in names):
        return 2
    return 3


RANK_LABEL = {0: "ID / VAT match", 1: "Exact name", 2: "Name contains", 3: "Fuzzy"}


def parse_matches(matches: list, term: str) -> list[dict]:
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
        rank = classify(term, pid.get("value", ""), identifiers, names)
        rows.append({
            "Search Value": term,
            "Match Type": RANK_LABEL[rank],
            "_rank": rank,
            "Company Name": "; ".join(dict.fromkeys(names)),
            "Participant ID": pid.get("value", ""),
            "Scheme": pid.get("scheme", ""),
            "Country": ", ".join(countries) or m.get("countryCode", ""),
            "Identifiers": "; ".join(dict.fromkeys(identifiers)),
            "Document Types": len(doc_types),
            "Accepts Invoice (BIS 3)": "Yes" if accepts_invoice else "No",
        })
    return rows


def mark_best(df: pd.DataFrame) -> pd.DataFrame:
    best = df.groupby("Search Value")["_rank"].transform("min")
    df["Best Match"] = ((df["_rank"] == best) & (df["_rank"] < 3)).map({True: "✔", False: ""})
    df = df.sort_values(["Search Value", "_rank"], kind="stable")
    return df.drop(columns="_rank")


def build_df(results: dict, terms: list[str], first_row: dict | None = None) -> pd.DataFrame:
    """Combine per-term rows (in input order) into one tidy DataFrame."""
    rows = [r for t in terms if t in results for r in results[t]]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "_rank" in df:
        ranked = mark_best(df[df["_rank"].notna()].copy())
        unranked = df[df["_rank"].isna()].drop(columns="_rank")
        df = pd.concat([ranked, unranked], ignore_index=True)
    if first_row:
        df["Input Row"] = df["Search Value"].map(first_row)
    order = {t: i for i, t in enumerate(terms)}
    df = df.sort_values("Search Value", key=lambda s: s.map(order), kind="stable")
    first = ["Input Row", "Search Value", "Status", "Best Match", "Match Type"]
    df = df[[c for c in first if c in df] + [c for c in df if c not in first]]
    return df.fillna("")


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """UTF-8 with BOM (Excel-friendly) and neutralised formula-injection prefixes."""
    safe = df.copy()
    for col in safe.select_dtypes(include="object").columns:
        safe[col] = safe[col].map(
            lambda v: "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v
        )
    return safe.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def search_one(term: str, env: str, country: str, size: int, max_pages: int, cache: dict) -> list[dict]:
    """Look up one term and return its result rows. Never raises."""
    try:
        data = lookup(term, env, country, size, max_pages, cache)
        rows = parse_matches(data["matches"], term)
        if not rows:
            return [{"Search Value": term, "Status": "NOT FOUND"}]
        shown, total = len(data["matches"]), data["total"]
        status = "OK" if shown >= total else f"OK (first {shown} of {total})"
        for r in rows:
            r["Status"] = status
        return rows
    except requests.RequestException as e:
        return [{"Search Value": term, "Status": f"ERROR: {type(e).__name__}"}]
    except Exception as e:
        return [{"Search Value": term, "Status": f"ERROR (parsing): {e}"}]


def has_error(rows: list[dict]) -> bool:
    return any(str(r.get("Status", "")).startswith("ERROR") for r in rows)


# =====================================================
# SETTINGS
# =====================================================

cache = get_cache()

environment = st.radio("Environment", ["PROD", "TEST"], horizontal=True)

with st.expander("Search settings"):
    c1, c2, c3 = st.columns(3)
    country_filter = c1.text_input(
        "Country filter (ISO-2, optional)",
        max_chars=2,
        help="Restricts name / VAT searches to one country. Much faster and more accurate.",
    ).strip().upper()
    bulk_size = c2.slider("Results per search (bulk)", 5, 100, 25,
                          help="Only the top matches per value are fetched. Lower = faster.")
    workers = c3.slider("Parallel requests", 1, 8, 4,
                        help="Raise carefully - this is a public service.")
    if st.button("Clear lookup cache"):
        with cache["lock"]:
            cache["data"].clear()
        st.session_state["bulk_store"] = {}
        st.toast("Cache and bulk results cleared")

# =====================================================
# SINGLE SEARCH
# =====================================================

with st.form("single_search"):
    search_value = st.text_input("Customer Name / VAT / Participant ID (e.g. 0208:0202239951)")
    max_single = st.selectbox("Max results", [100, 300, 1000], index=0)
    submitted = st.form_submit_button("Search")

if submitted and search_value.strip():
    term = search_value.strip()
    try:
        with st.spinner("Searching..."):
            data = lookup(term, environment, country_filter, 100, math.ceil(max_single / 100), cache)
        rows = parse_matches(data["matches"], term)
        df = mark_best(pd.DataFrame(rows)).fillna("") if rows else pd.DataFrame()
        st.session_state["single"] = {
            "df": df, "total": data["total"], "fetched": len(data["matches"]), "term": term,
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
            f"Showing {single['fetched']} of {single['total']} results. "
            "Add a country filter, a more specific name, or raise Max results."
        )
    if single["df"].empty:
        st.info("No matches found.")
    else:
        st.dataframe(single["df"], width="stretch", height=600)
        st.download_button("⬇ Download Results", to_csv_bytes(single["df"]),
                           "peppol_results.csv", "text/csv")

# =====================================================
# BULK SEARCH (row ranges / batches)
# =====================================================

st.divider()
st.subheader("Bulk Search")

uploaded = st.file_uploader("Upload Excel or CSV", type=["xlsx", "csv"])

if uploaded:
    has_header = st.checkbox("First row is a header", value=True)
    header = 0 if has_header else None
    try:
        if uploaded.name.lower().endswith(".csv"):
            in_df = pd.read_csv(uploaded, header=header, dtype=str, keep_default_na=False)
        else:
            in_df = pd.read_excel(uploaded, header=header, dtype=str).fillna("")
    except Exception as e:
        st.error(f"Could not read file: {e}")
        st.stop()

    in_df.columns = [str(c) for c in in_df.columns]
    column = st.selectbox("Column to search", in_df.columns, index=0)

    raw_terms = [str(v).strip() for v in in_df[column]]
    n_rows = len(raw_terms)
    if n_rows == 0:
        st.warning("The file has no data rows.")
        st.stop()

    def valid(t: str) -> bool:
        return bool(t) and t.lower() != "nan"

    # Unique non-empty values in file order, plus the first file row each appears in
    all_terms: list[str] = []
    first_row: dict[str, int] = {}
    for i, t in enumerate(raw_terms, start=1):
        if valid(t) and t not in first_row:
            first_row[t] = i
            all_terms.append(t)

    st.write(f"{n_rows} data rows in file, {len(all_terms)} unique values.")
    st.dataframe(in_df.head(20), width="stretch")

    # ---- Row range selector ----
    st.markdown("**Choose the rows to look up** (row numbers of the data rows, header excluded)")
    kfx = f"{uploaded.name}_{n_rows}"
    r1, r2 = st.columns(2)
    start = int(r1.number_input("From row", min_value=1, max_value=n_rows, value=1,
                                step=1, key=f"from_{kfx}"))
    end = int(r2.number_input("To row", min_value=1, max_value=n_rows, value=min(500, n_rows),
                              step=1, key=f"to_{kfx}"))
    if start > end:
        st.error("'From row' must be less than or equal to 'To row'.")
        st.stop()

    range_terms = list(dict.fromkeys(t for t in raw_terms[start - 1:end] if valid(t)))

    # Results are stored per (environment, country, size) so settings changes never mix results
    ctx = (environment, country_filter, bulk_size)
    if "bulk_store" not in st.session_state:
        st.session_state["bulk_store"] = {}
    results: dict[str, list] = st.session_state["bulk_store"].setdefault(ctx, {})

    def is_done(t: str) -> bool:
        return t in results and not has_error(results[t])

    todo = [t for t in range_terms if not is_done(t)]
    done_total = sum(is_done(t) for t in all_terms)
    st.caption(
        f"Rows {start}-{end}: {len(range_terms)} unique values, "
        f"{len(range_terms) - len(todo)} already done, {len(todo)} to look up. "
        f"Overall progress: {done_total}/{len(all_terms)} values done."
    )

    if st.button(f"Lookup rows {start}-{end}"):
        if not todo:
            st.info("Everything in this range is already done. Download it below.")
        else:
            progress = st.progress(0.0, text="Starting...")
            live = st.empty()
            pool = ThreadPoolExecutor(max_workers=workers)
            try:
                futures = [
                    pool.submit(search_one, t, environment, country_filter, bulk_size, 1, cache)
                    for t in todo
                ]
                for done, fut in enumerate(as_completed(futures), start=1):
                    rows = fut.result()
                    results[rows[0]["Search Value"]] = rows   # saved immediately, survives interruptions
                    progress.progress(done / len(todo), text=f"{done}/{len(todo)} looked up")
                    if done % 10 == 0:
                        live.dataframe(build_df(results, range_terms, first_row).tail(15),
                                       width="stretch")
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
            live.empty()
            progress.empty()

    # ---- Results + downloads ----
    range_df = build_df(results, range_terms, first_row)
    all_df = build_df(results, all_terms, first_row)

    if range_df.empty:
        st.info(f"No results yet for rows {start}-{end}. Click the Lookup button.")
    else:
        pending = [t for t in range_terms if not is_done(t)]
        n_nf = int((range_df["Status"] == "NOT FOUND").sum())
        n_err = int(range_df["Status"].astype(str).str.startswith("ERROR").sum())
        msg = (f"Rows {start}-{end}: {len(range_terms) - len(pending)}/{len(range_terms)} values done -> "
               f"{len(range_df)} rows ({n_nf} not found, {n_err} errors)")
        if pending:
            st.warning(msg + f". {len(pending)} values not finished - click Lookup again to "
                             "resume (finished values are kept; errors are retried).")
        else:
            st.success(msg)

        st.dataframe(range_df, width="stretch", height=600)

        d1, d2 = st.columns(2)
        d1.download_button(
            f"⬇ Download rows {start}-{end}",
            to_csv_bytes(range_df),
            f"peppol_rows_{start}-{end}.csv",
            "text/csv",
        )
        d2.download_button(
            f"⬇ Download everything done so far ({len(all_terms) and done_total}/{len(all_terms)} values)",
            to_csv_bytes(all_df),
            "peppol_all_results.csv",
            "text/csv",
        )
