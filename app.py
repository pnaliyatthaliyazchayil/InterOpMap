"""
UMLS Terminology Toolkit — Streamlit UI
Tab 1: Crosswalk — Upload CSV of codes → map to any vocabulary → download
Tab 2: Value Set Builder — Search concepts → navigate tree → build value sets
"""

import streamlit as st
import pandas as pd
import requests
import time
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="UMLS Toolkit",
    page_icon="🧬",
    layout="wide",
)

# ── Custom CSS — Sea Green Theme ─────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
    }
    
    .hero-banner {
        background: linear-gradient(135deg, #064e3b 0%, #047857 50%, #059669 100%);
        border-radius: 16px;
        padding: 2.5rem 2rem;
        margin-bottom: 2rem;
        border: 1px solid rgba(16, 185, 129, 0.3);
        position: relative;
        overflow: hidden;
    }
    .hero-banner::before {
        content: '';
        position: absolute;
        top: -50%;
        right: -20%;
        width: 400px;
        height: 400px;
        background: radial-gradient(circle, rgba(16,185,129,0.12) 0%, transparent 70%);
        border-radius: 50%;
    }
    .hero-banner h1 {
        color: #ecfdf5;
        font-size: 2rem;
        font-weight: 700;
        margin: 0 0 0.5rem 0;
        letter-spacing: -0.5px;
    }
    .hero-banner p {
        color: #a7f3d0;
        font-size: 1rem;
        margin: 0;
        font-weight: 400;
    }

    .metric-row {
        display: flex;
        gap: 1rem;
        margin: 1rem 0;
    }
    .metric-card {
        flex: 1;
        background: #f0fdf4;
        border: 1px solid #d1fae5;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
    }
    .metric-card .value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #064e3b;
        font-family: 'JetBrains Mono', monospace;
    }
    .metric-card .label {
        font-size: 0.8rem;
        color: #059669;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 0.25rem;
    }

    .step-header {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 1rem;
    }
    .step-number {
        background: #047857;
        color: white;
        width: 32px;
        height: 32px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.85rem;
        flex-shrink: 0;
    }
    .step-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #064e3b;
    }

    .info-box {
        background: #ecfdf5;
        border-left: 4px solid #10b981;
        padding: 1rem 1.25rem;
        border-radius: 0 8px 8px 0;
        margin: 1rem 0;
        font-size: 0.9rem;
        color: #065f46;
    }

    .disclaimer {
        background: #fffbeb;
        border: 1px solid #fde68a;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-size: 0.8rem;
        color: #92400e;
        margin: 1rem 0;
    }

    .concept-pill {
        display: inline-block;
        background: #ecfdf5;
        border: 1px solid #a7f3d0;
        color: #065f46;
        padding: 0.25rem 0.75rem;
        border-radius: 999px;
        font-size: 0.85rem;
        margin: 0.25rem;
        font-family: 'JetBrains Mono', monospace;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    [data-testid="stFileUploader"] {
        border: 2px dashed #a7f3d0;
        border-radius: 12px;
        padding: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ── UMLS vocabulary abbreviations ────────────────────────────────────────────
VOCAB_OPTIONS = {
    "ICD-10-CM (US Clinical Modification)": "ICD10CM",
    "ICD-10-PCS (Procedure Coding System)": "ICD10PCS",
    "ICD-9-CM (Diagnoses)": "ICD9CM",
    "SNOMED CT (US Edition)": "SNOMEDCT_US",
    "SNOMED CT (International)": "SNOMEDCT",
    "CPT (Current Procedural Terminology)": "CPT",
    "HCPCS (Healthcare Common Procedure)": "HCPCS",
    "LOINC (Lab Observations)": "LNC",
    "RxNorm (Drug Names)": "RXNORM",
    "MeSH (Medical Subject Headings)": "MSH",
    "NCI Thesaurus": "NCI",
    "HPO (Human Phenotype Ontology)": "HPO",
    "OMIM (Online Mendelian Inheritance)": "OMIM",
    "NDC (National Drug Code)": "NDC",
    "CVX (Vaccine Codes)": "CVX",
    "DSM-5 (Diagnostic & Statistical Manual)": "DSM5",
    "MedDRA (Medical Dictionary for Regulatory)": "MDR",
    "VANDF (VA National Drug File)": "VANDF",
    "GO (Gene Ontology)": "GO",
    "HL7 (Health Level 7 Vocabulary)": "HL7V3.0",
}

UMLS_BASE = "https://uts-ws.nlm.nih.gov/rest"

# ── API helpers ──────────────────────────────────────────────────────────────
def crosswalk_code(api_key: str, source_vocab: str, code: str, target_vocab: str):
    """Call the UMLS crosswalk endpoint for a single code."""
    url = f"{UMLS_BASE}/crosswalk/current/source/{source_vocab}/{code}"
    params = {
        "apiKey": api_key,
        "targetSource": target_vocab,
        "pageSize": 25,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 401:
            return {"error": "Invalid API key"}
        if resp.status_code == 404:
            return {"error": "Code not found in source vocabulary"}
        if resp.status_code == 403:
            return {"error": "Access denied — check your UMLS license"}
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}
        
        data = resp.json()
        results = data.get("result", [])
        if not results:
            return {"error": "No mapping found"}
        
        mapped = []
        for r in results:
            mapped.append({
                "target_code": r.get("ui", ""),
                "target_name": r.get("name", ""),
                "target_vocab": r.get("rootSource", target_vocab),
                "obsolete": r.get("obsolete", False),
            })
        return {"results": mapped}
    
    except requests.exceptions.Timeout:
        return {"error": "Request timed out"}
    except requests.exceptions.ConnectionError:
        return {"error": "Connection failed"}
    except Exception as e:
        return {"error": str(e)}


def validate_api_key(api_key: str) -> bool:
    """Quick check that the API key works."""
    url = f"{UMLS_BASE}/content/current/CUI/C0009044"
    params = {"apiKey": api_key}
    try:
        resp = requests.get(url, params=params, timeout=15)
        return resp.status_code == 200
    except Exception:
        return False


def process_batch(api_key, source_vocab, target_vocab, codes, progress_bar, status_text):
    """Process a list of codes through the crosswalk API."""
    results = [None] * len(codes)
    completed = 0
    total = len(codes)
    max_workers = min(4, total)
    
    def do_one(idx, code):
        return idx, crosswalk_code(api_key, source_vocab, str(code).strip(), target_vocab)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(do_one, i, c): i for i, c in enumerate(codes)}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result
            completed += 1
            pct = completed / total
            progress_bar.progress(pct, text=f"Processing {completed}/{total} codes…")
            status_text.markdown(
                f"<span style='font-family: JetBrains Mono; font-size: 0.85rem; color: #059669;'>"
                f"Latest: code #{idx+1} — "
                f"{'✅ mapped' if 'results' in result else '⚠️ ' + result.get('error', 'unknown')}"
                f"</span>",
                unsafe_allow_html=True
            )
            time.sleep(0.05)
    
    return results


# ── UI ───────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="hero-banner">
    <h1>🧬 UMLS Terminology Toolkit</h1>
    <p>Code crosswalking • Value set builder • Powered by NLM UMLS API</p>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    
    api_key = st.text_input(
        "UMLS API Key",
        type="password",
        help="Get your free API key at https://uts.nlm.nih.gov/uts/profile",
        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    )
    
    if api_key:
        with st.spinner("Validating key…"):
            if validate_api_key(api_key):
                st.success("API key valid ✓")
            else:
                st.error("Invalid API key. Check your UTS profile.")
                api_key = None
    
    st.markdown("---")
    
    st.markdown("### 📖 Source Vocabulary")
    source_label = st.selectbox(
        "What vocabulary are your codes in?",
        options=list(VOCAB_OPTIONS.keys()),
        index=0,
        help="The coding system your uploaded codes belong to"
    )
    source_vocab = VOCAB_OPTIONS[source_label]
    
    st.markdown("### 🎯 Target Vocabulary")
    target_options = {k: v for k, v in VOCAB_OPTIONS.items() if v != source_vocab}
    target_label = st.selectbox(
        "What vocabulary do you want to map to?",
        options=list(target_options.keys()),
        index=list(target_options.keys()).index("SNOMED CT (US Edition)") 
              if "SNOMED CT (US Edition)" in target_options else 0,
        help="The target coding system for the crosswalk"
    )
    target_vocab = target_options[target_label]
    
    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.75rem; color:#059669;'>"
        "Powered by NLM UMLS REST API<br>"
        "Free license at <a href='https://uts.nlm.nih.gov' target='_blank'>uts.nlm.nih.gov</a>"
        "</div>",
        unsafe_allow_html=True
    )

# Main tabs
tab1, tab2 = st.tabs(["🔀 Crosswalk", "📋 Value Set Builder"])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: CROSSWALK
# ═══════════════════════════════════════════════════════════════════════════

with tab1:
    st.markdown("""
    <div class="info-box">
        Upload a CSV of medical codes → select the code column → map to target vocabulary → download enriched CSV
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "Choose a CSV file",
        type=["csv"],
        help="Max recommended: ~5,000 rows (API rate limits apply)"
    )

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Could not parse CSV: {e}")
            st.stop()
        
        st.markdown(f"**Preview** — {len(df):,} rows × {len(df.columns)} columns")
        st.dataframe(df.head(10), use_container_width=True, height=280)
        
        col1, col2 = st.columns(2)
        with col1:
            code_column = st.selectbox(
                "Which column contains the source codes?",
                options=df.columns.tolist(),
                help="Select the column that holds ICD, SNOMED, LOINC (etc.) codes"
            )
        with col2:
            st.markdown(f"**Mapping direction:**")
            st.markdown(f"`{source_vocab}` → `{target_vocab}`")
            unique_codes = df[code_column].dropna().nunique()
            st.markdown(f"Unique codes to map: **{unique_codes:,}**")
        
        sample_codes = df[code_column].dropna().unique()[:5]
        st.markdown(f"Sample codes: `{'`, `'.join(str(c) for c in sample_codes)}`")
        
        st.markdown("""
        <div class="disclaimer">
            ⚠️ <strong>Important:</strong> UMLS crosswalk mappings are based on CUI synonymy and have 
            <em>not been rigorously tested in clinical care</em>. Results should be reviewed by a qualified 
            coding professional before use in billing, clinical, or regulatory workflows.
        </div>
        """, unsafe_allow_html=True)
        
        if not api_key:
            st.warning("Enter your UMLS API key in the sidebar to proceed.")
            st.stop()
        
        run_button = st.button(
            "🚀 Start Crosswalk",
            type="primary",
            use_container_width=True,
        )
        
        if run_button:
            codes = df[code_column].astype(str).tolist()
            unique_list = list(dict.fromkeys(codes))
            
            st.markdown(f"Processing **{len(unique_list):,}** unique codes ({len(codes):,} total rows)…")
            
            progress_bar = st.progress(0, text="Starting…")
            status_text = st.empty()
            
            start_time = time.time()
            raw_results = process_batch(
                api_key, source_vocab, target_vocab,
                unique_list, progress_bar, status_text
            )
            elapsed = time.time() - start_time
            
            progress_bar.progress(1.0, text="Complete!")
            
            lookup = dict(zip(unique_list, raw_results))
            
            out_rows = []
            mapped_count = 0
            unmapped_count = 0
            multi_map_count = 0
            
            for _, row in df.iterrows():
                code = str(row[code_column]).strip()
                result = lookup.get(code, {"error": "Not processed"})
                
                if "results" in result and result["results"]:
                    mappings = result["results"]
                    if len(mappings) > 1:
                        multi_map_count += 1
                    mapped_count += 1
                    for m in mappings:
                        out_row = row.to_dict()
                        out_row["target_code"] = m["target_code"]
                        out_row["target_name"] = m["target_name"]
                        out_row["target_vocabulary"] = m["target_vocab"]
                        out_row["mapping_status"] = "mapped"
                        out_row["is_obsolete"] = m["obsolete"]
                        out_rows.append(out_row)
                else:
                    unmapped_count += 1
                    out_row = row.to_dict()
                    out_row["target_code"] = ""
                    out_row["target_name"] = ""
                    out_row["target_vocabulary"] = target_vocab
                    out_row["mapping_status"] = result.get("error", "unmapped")
                    out_row["is_obsolete"] = False
                    out_rows.append(out_row)
            
            result_df = pd.DataFrame(out_rows)
            
            st.session_state["result_df"] = result_df
            st.session_state["stats"] = {
                "mapped": mapped_count,
                "unmapped": unmapped_count,
                "multi": multi_map_count,
                "total": len(codes),
                "unique": len(unique_list),
                "elapsed": elapsed,
                "output_rows": len(result_df),
            }
        
        if "result_df" in st.session_state:
            result_df = st.session_state["result_df"]
            stats = st.session_state["stats"]
            
            st.markdown("### Results & Export")
            
            map_rate = (stats["mapped"] / stats["unique"] * 100) if stats["unique"] > 0 else 0
            st.markdown(f"""
            <div class="metric-row">
                <div class="metric-card">
                    <div class="value">{stats['unique']:,}</div>
                    <div class="label">Unique Codes</div>
                </div>
                <div class="metric-card">
                    <div class="value">{stats['mapped']:,}</div>
                    <div class="label">Mapped ✓</div>
                </div>
                <div class="metric-card">
                    <div class="value">{stats['unmapped']:,}</div>
                    <div class="label">Unmapped</div>
                </div>
                <div class="metric-card">
                    <div class="value">{map_rate:.1f}%</div>
                    <div class="label">Map Rate</div>
                </div>
                <div class="metric-card">
                    <div class="value">{stats['elapsed']:.1f}s</div>
                    <div class="label">Elapsed</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            if stats["multi"] > 0:
                st.info(
                    f"ℹ️ {stats['multi']} codes had **1-to-many** mappings. "
                    f"Output has {stats['output_rows']:,} rows (expanded from {stats['total']:,} input rows)."
                )
            
            tab_all, tab_mapped, tab_unmapped = st.tabs(["All Results", "Mapped Only", "Unmapped Only"])
            
            with tab_all:
                st.dataframe(result_df, use_container_width=True, height=400)
            with tab_mapped:
                mapped_df = result_df[result_df["mapping_status"] == "mapped"]
                st.dataframe(mapped_df, use_container_width=True, height=400)
            with tab_unmapped:
                unmapped_df = result_df[result_df["mapping_status"] != "mapped"]
                st.dataframe(unmapped_df, use_container_width=True, height=400)
            
            st.markdown("### 📥 Download Results")
            
            col_a, col_b, col_c = st.columns(3)
            
            csv_all = result_df.to_csv(index=False)
            col_a.download_button(
                label="⬇ All Results (CSV)",
                data=csv_all,
                file_name=f"crosswalk_{source_vocab}_to_{target_vocab}_all.csv",
                mime="text/csv",
                use_container_width=True,
            )
            
            csv_mapped = result_df[result_df["mapping_status"] == "mapped"].to_csv(index=False)
            col_b.download_button(
                label="⬇ Mapped Only (CSV)",
                data=csv_mapped,
                file_name=f"crosswalk_{source_vocab}_to_{target_vocab}_mapped.csv",
                mime="text/csv",
                use_container_width=True,
            )
            
            csv_unmapped = result_df[result_df["mapping_status"] != "mapped"].to_csv(index=False)
            col_c.download_button(
                label="⬇ Unmapped Only (CSV)",
                data=csv_unmapped,
                file_name=f"crosswalk_{source_vocab}_to_{target_vocab}_unmapped.csv",
                mime="text/csv",
                use_container_width=True,
            )

    else:
        st.markdown("### Supported Crosswalk Paths")
        st.markdown(
            "The UMLS Metathesaurus links **200+ vocabularies** via Concept Unique Identifiers (CUIs). "
            "Any pair of vocabularies that share CUIs can be crosswalked."
        )
        
        paths = [
            ("ICD-9-CM", "→", "ICD-10-CM", "Diagnosis migration"),
            ("ICD-10-CM", "→", "SNOMED CT", "Clinical ↔ billing bridge"),
            ("SNOMED CT", "→", "ICD-10-CM", "EHR to claims"),
            ("CPT", "→", "SNOMED CT", "Procedure mapping"),
            ("LOINC", "→", "SNOMED CT", "Lab observation mapping"),
            ("RxNorm", "→", "NDC", "Drug code mapping"),
        ]
        
        path_df = pd.DataFrame(paths, columns=["Source", "", "Target", "Use Case"])
        st.dataframe(path_df, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: VALUE SET BUILDER
# ═══════════════════════════════════════════════════════════════════════════

with tab2:
    st.markdown("""
    <div class="info-box">
        Build value sets by exploring UMLS hierarchies. Search for a concept, navigate up/down 
        the tree, and check concepts to include them in your value set. Supports SNOMED CT, 
        ICD-10-CM, LOINC, and other hierarchical vocabularies.
    </div>
    """, unsafe_allow_html=True)
    
    if not api_key:
        st.warning("Enter your UMLS API key in the sidebar to proceed.")
        st.stop()
    
    # Initialize session state
    if "value_set" not in st.session_state:
        st.session_state["value_set"] = []
    
    col_left, col_right = st.columns([3, 2])
    
    with col_left:
        st.markdown("### 🔍 Search & Navigate")
        
        search_vocab = st.selectbox(
            "Vocabulary",
            options=list(VOCAB_OPTIONS.keys()),
            index=list(VOCAB_OPTIONS.keys()).index("SNOMED CT (US Edition)"),
            key="vs_vocab"
        )
        search_vocab_code = VOCAB_OPTIONS[search_vocab]
        
        search_term = st.text_input(
            "Search for a concept",
            placeholder="e.g., diabetes, hypertension, pneumonia",
            key="vs_search"
        )
        
        if st.button("🔎 Search", type="primary", use_container_width=True):
            if not search_term:
                st.warning("Enter a search term")
            else:
                with st.spinner("Searching UMLS…"):
                    url = f"{UMLS_BASE}/search/current"
                    params = {
                        "apiKey": api_key,
                        "string": search_term,
                        "sabs": search_vocab_code,
                        "returnIdType": "code",
                        "pageSize": 20,
                    }
                    try:
                        resp = requests.get(url, params=params, timeout=30)
                        if resp.status_code == 200:
                            data = resp.json()
                            results = data.get("result", {}).get("results", [])
                            if results:
                                st.session_state["search_results"] = results
                            else:
                                st.info("No results found")
                        else:
                            st.error(f"Search failed: HTTP {resp.status_code}")
                    except Exception as e:
                        st.error(f"Error: {e}")
        
        # Display search results
        if "search_results" in st.session_state:
            results = st.session_state["search_results"]
            st.markdown(f"**{len(results)} results:**")
            
            for r in results:
                ui = r.get("ui", "")
                name = r.get("name", "Unknown")
                source = r.get("rootSource", search_vocab_code)
                
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"**{name}**  \n`{ui}` • {source}")
                with col2:
                    if st.button("Explore", key=f"explore_{ui}"):
                        st.session_state["current_code"] = ui
                        st.session_state["current_vocab"] = source
                        st.session_state["current_name"] = name
                        st.rerun()
        
        # Tree navigation
        if "current_code" in st.session_state:
            st.markdown("---")
            st.markdown("### 🌳 Hierarchy Navigator")
            
            current_code = st.session_state["current_code"]
            current_vocab = st.session_state["current_vocab"]
            current_name = st.session_state.get("current_name", current_code)
            
            st.markdown(f"**Current:** `{current_code}` — {current_name}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("⬆️ Show Parents", use_container_width=True):
                    url = f"{UMLS_BASE}/content/current/source/{current_vocab}/{current_code}/parents"
                    params = {"apiKey": api_key, "pageSize": 50}
                    try:
                        resp = requests.get(url, params=params, timeout=30)
                        if resp.status_code == 200:
                            data = resp.json()
                            st.session_state["parents"] = data.get("result", [])
                        else:
                            st.session_state["parents"] = []
                    except Exception:
                        st.session_state["parents"] = []
            
            with col2:
                if st.button("⬇️ Show Children", use_container_width=True):
                    url = f"{UMLS_BASE}/content/current/source/{current_vocab}/{current_code}/children"
                    params = {"apiKey": api_key, "pageSize": 50}
                    try:
                        resp = requests.get(url, params=params, timeout=30)
                        if resp.status_code == 200:
                            data = resp.json()
                            st.session_state["children"] = data.get("result", [])
                        else:
                            st.session_state["children"] = []
                    except Exception:
                        st.session_state["children"] = []
            
            # Display parents
            if "parents" in st.session_state and st.session_state["parents"]:
                st.markdown("**Parents (broader concepts):**")
                for p in st.session_state["parents"]:
                    ui = p.get("ui", "")
                    name = p.get("name", "Unknown")
                    col1, col2, col3 = st.columns([1, 5, 1])
                    with col1:
                        checked = any(c["code"] == ui for c in st.session_state["value_set"])
                        if st.checkbox("", key=f"chk_p_{ui}", value=checked):
                            if not checked:
                                st.session_state["value_set"].append({
                                    "code": ui,
                                    "name": name,
                                    "vocab": current_vocab
                                })
                                st.rerun()
                        elif checked:
                            st.session_state["value_set"] = [
                                c for c in st.session_state["value_set"] if c["code"] != ui
                            ]
                            st.rerun()
                    with col2:
                        st.markdown(f"↑ {name} `{ui}`")
                    with col3:
                        if st.button("→", key=f"nav_p_{ui}"):
                            st.session_state["current_code"] = ui
                            st.session_state["current_name"] = name
                            st.rerun()
            
            # Display children
            if "children" in st.session_state and st.session_state["children"]:
                st.markdown("**Children (narrower concepts):**")
                for c in st.session_state["children"]:
                    ui = c.get("ui", "")
                    name = c.get("name", "Unknown")
                    col1, col2, col3 = st.columns([1, 5, 1])
                    with col1:
                        checked = any(x["code"] == ui for x in st.session_state["value_set"])
                        if st.checkbox("", key=f"chk_c_{ui}", value=checked):
                            if not checked:
                                st.session_state["value_set"].append({
                                    "code": ui,
                                    "name": name,
                                    "vocab": current_vocab
                                })
                                st.rerun()
                        elif checked:
                            st.session_state["value_set"] = [
                                x for x in st.session_state["value_set"] if x["code"] != ui
                            ]
                            st.rerun()
                    with col2:
                        st.markdown(f"↓ {name} `{ui}`")
                    with col3:
                        if st.button("→", key=f"nav_c_{ui}"):
                            st.session_state["current_code"] = ui
                            st.session_state["current_name"] = name
                            st.rerun()
    
    with col_right:
        st.markdown("### 📋 Your Value Set")
        
        value_set = st.session_state["value_set"]
        
        if value_set:
            st.markdown(f"**{len(value_set)} concepts selected:**")
            
            for i, item in enumerate(value_set):
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"""
                    <div class="concept-pill">
                        {item['code']} — {item['name'][:40]}{'...' if len(item['name']) > 40 else ''}
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    if st.button("✕", key=f"rm_{i}"):
                        st.session_state["value_set"].pop(i)
                        st.rerun()
            
            st.markdown("---")
            if st.button("Clear All", use_container_width=True):
                st.session_state["value_set"] = []
                st.rerun()
            
            vs_df = pd.DataFrame(value_set)
            csv = vs_df.to_csv(index=False)
            st.download_button(
                label="⬇ Download Value Set (CSV)",
                data=csv,
                file_name=f"value_set_{search_vocab_code}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.info("No concepts added yet. Search and explore the hierarchy to build your value set.")
