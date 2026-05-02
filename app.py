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
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.5rem;
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
        font-size: 1.5rem;
        font-weight: 700;
        margin: 0 0 0.25rem 0;
        letter-spacing: -0.5px;
    }
    .hero-banner p {
        color: #a7f3d0;
        font-size: 0.85rem;
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

# Main tabs
tab1, tab2 = st.tabs(["🔀 Crosswalk", "📋 Value Set Builder"])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: CROSSWALK
# ═══════════════════════════════════════════════════════════════════════════

with tab1:
    # Remove sidebar - put everything inline
    
    st.markdown("""
    <div class="step-header">
        <div class="step-number">1</div>
        <div class="step-title">Enter API Key</div>
    </div>
    """, unsafe_allow_html=True)
    
    api_key_input = st.text_input(
        "UMLS API Key",
        type="password",
        help="Get your free API key at https://uts.nlm.nih.gov/uts/profile",
        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        key="crosswalk_api_key"
    )
    
    if not api_key_input:
        st.info("👆 Enter your UMLS API key to run crosswalks. [Get one free here →](https://uts.nlm.nih.gov/uts/profile)")
    # Don't validate or stop here - let them see the whole interface first
    
    # Step 2: Source & Target
    st.markdown("""
    <div class="step-header">
        <div class="step-number">2</div>
        <div class="step-title">Select Source & Target Vocabularies</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        source_label = st.selectbox(
            "📖 Source Vocabulary (what you have)",
            options=list(VOCAB_OPTIONS.keys()),
            index=0,
            key="crosswalk_source"
        )
        source_vocab = VOCAB_OPTIONS[source_label]
    
    with col2:
        target_options = {k: v for k, v in VOCAB_OPTIONS.items() if v != source_vocab}
        target_label = st.selectbox(
            "🎯 Target Vocabulary (what you want)",
            options=list(target_options.keys()),
            index=list(target_options.keys()).index("SNOMED CT (US Edition)") 
                  if "SNOMED CT (US Edition)" in target_options else 0,
            key="crosswalk_target"
        )
        target_vocab = target_options[target_label]
    
    st.markdown(f"**Mapping:** `{source_vocab}` → `{target_vocab}`")
    
    # Step 3: Upload
    st.markdown("""
    <div class="step-header">
        <div class="step-number">3</div>
        <div class="step-title">Upload CSV</div>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader(
        "Choose a CSV file containing your codes",
        type=["csv"],
        help="Max recommended: ~5,000 rows (API rate limits apply)"
    )

    if uploaded_file is None:
        st.info("👆 Upload a CSV file with a column of medical codes")
        
        # Show example at bottom
        with st.expander("📋 See supported crosswalk paths"):
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
        st.stop()
    
    try:
        df = pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Could not parse CSV: {e}")
        st.stop()
    
    # Step 4: Select code column
    st.markdown("""
    <div class="step-header">
        <div class="step-number">4</div>
        <div class="step-title">Select Code Column</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    with col1:
        code_column = st.selectbox(
            "Which column contains the source codes?",
            options=df.columns.tolist(),
            help="Select the column with ICD, SNOMED, LOINC, etc. codes"
        )
    with col2:
        unique_codes = df[code_column].dropna().nunique()
        st.metric("Unique codes", f"{unique_codes:,}")
    
    sample_codes = df[code_column].dropna().unique()[:3]
    st.caption(f"Sample codes from `{code_column}`: `{'`, `'.join(str(c) for c in sample_codes)}`")

    
    # Step 5: Run
    st.markdown("""
    <div class="step-header">
        <div class="step-number">5</div>
        <div class="step-title">Run Crosswalk</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="disclaimer">
        ⚠️ <strong>Disclaimer:</strong> UMLS crosswalk mappings are based on CUI synonymy and have 
        <em>not been rigorously tested in clinical care</em>. Review results before use in production.
    </div>
    """, unsafe_allow_html=True)
    
    run_button = st.button(
        "🚀 Start Crosswalk",
        type="primary",
        use_container_width=True,
    )
    
    if run_button:
        # Validate API key NOW (when button is clicked)
        if not api_key_input:
            st.error("❌ Please enter your UMLS API key in Step 1")
            st.stop()
        
        with st.spinner("Validating API key..."):
            if not validate_api_key(api_key_input):
                st.error("❌ Invalid API key. Please check your UTS profile and try again.")
                st.stop()
        
        st.success("✅ API key valid - starting crosswalk...")
        
        codes = df[code_column].astype(str).tolist()
        unique_list = list(dict.fromkeys(codes))
        
        st.markdown(f"Processing **{len(unique_list):,}** unique codes ({len(codes):,} total rows)…")
        
        progress_bar = st.progress(0, text="Starting…")
        status_text = st.empty()
        
        start_time = time.time()
        raw_results = process_batch(
            api_key_input, source_vocab, target_vocab,
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
        
        st.markdown("---")
        st.markdown("### 📊 Crosswalk Complete!")
        
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
        
        st.markdown("#### 👁 Preview Results")
        tab_all, tab_mapped, tab_unmapped = st.tabs(["All Results", "Mapped Only", "Unmapped Only"])
        
        with tab_all:
            st.dataframe(result_df.head(100), use_container_width=True, height=250)
            st.caption(f"Showing first 100 of {len(result_df):,} rows")
        with tab_mapped:
            mapped_df = result_df[result_df["mapping_status"] == "mapped"]
            st.dataframe(mapped_df.head(100), use_container_width=True, height=250)
            st.caption(f"Showing first 100 of {len(mapped_df):,} mapped rows")
        with tab_unmapped:
            unmapped_df = result_df[result_df["mapping_status"] != "mapped"]
            st.dataframe(unmapped_df.head(100), use_container_width=True, height=250)
            st.caption(f"Showing first 100 of {len(unmapped_df):,} unmapped rows")
        
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



# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: VALUE SET BUILDER
# ═══════════════════════════════════════════════════════════════════════════

with tab2:
    st.markdown("""
    <div class="info-box">
        Build custom value sets by searching concepts and navigating hierarchies. 
        Perfect for creating cohorts, inclusion criteria, or standardized code lists.
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    if "value_set" not in st.session_state:
        st.session_state["value_set"] = []
    if "vs_name" not in st.session_state:
        st.session_state["vs_name"] = ""
    
    # Step 1: API Key
    st.markdown("""
    <div class="step-header">
        <div class="step-number">1</div>
        <div class="step-title">Enter API Key</div>
    </div>
    """, unsafe_allow_html=True)
    
    api_key_vs = st.text_input(
        "UMLS API Key",
        type="password",
        help="Get your free API key at https://uts.nlm.nih.gov/uts/profile",
        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        key="valueset_api_key"
    )
    
    if not api_key_vs:
        st.info("👆 Enter your UMLS API key to search and build value sets. [Get one free here →](https://uts.nlm.nih.gov/uts/profile)")
    # Don't stop - show the interface
    
    # Step 2: Name your value set
    st.markdown("""
    <div class="step-header">
        <div class="step-number">2</div>
        <div class="step-title">Name Your Value Set</div>
    </div>
    """, unsafe_allow_html=True)
    
    vs_name = st.text_input(
        "Value Set Name",
        value=st.session_state.get("vs_name", ""),
        placeholder="e.g., Antibiotics, Diabetes Diagnoses, Cardiac Procedures",
        help="Give your value set a descriptive name",
        key="vs_name_input"
    )
    
    if vs_name and vs_name != st.session_state.get("vs_name", ""):
        st.session_state["vs_name"] = vs_name
    
    # Step 3: Search & Add Concepts
    st.markdown("""
    <div class="step-header">
        <div class="step-number">3</div>
        <div class="step-title">Search & Add Concepts</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 2])
    
    with col1:
        # Vocabulary selector
        search_vocab = st.selectbox(
            "Vocabulary",
            options=list(VOCAB_OPTIONS.keys()),
            index=list(VOCAB_OPTIONS.keys()).index("SNOMED CT (US Edition)"),
            key="vs_vocab"
        )
        search_vocab_code = VOCAB_OPTIONS[search_vocab]
        
        # Search box
        search_term = st.text_input(
            "Search for a concept",
            placeholder="e.g., amoxicillin, type 2 diabetes, hypertension",
            key="vs_search"
        )
        
        if st.button("🔎 Search", type="primary", use_container_width=True):
            if not api_key_vs:
                st.error("❌ Please enter your API key in Step 1")
            elif not search_term:
                st.warning("Please enter a search term")
            else:
                # Validate API key on search
                with st.spinner("Validating API key..."):
                    if not validate_api_key(api_key_vs):
                        st.error("❌ Invalid API key. Please check your UTS profile.")
                        st.stop()
                
                with st.spinner("Searching UMLS…"):
                    url = f"{UMLS_BASE}/search/current"
                    params = {
                        "apiKey": api_key_vs,
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
                                st.session_state["current_code"] = None  # Clear navigation
                            else:
                                st.info("No results found")
                        else:
                            st.error(f"Search failed: HTTP {resp.status_code}")
                    except Exception as e:
                        st.error(f"Error: {e}")
        
        # Display search results
        if "search_results" in st.session_state and not st.session_state.get("current_code"):
            results = st.session_state["search_results"]
            st.markdown(f"**Found {len(results)} concepts:**")
            
            for r in results:
                ui = r.get("ui", "")
                name = r.get("name", "Unknown")
                source = r.get("rootSource", search_vocab_code)
                
                col_a, col_b, col_c = st.columns([1, 5, 1])
                
                with col_a:
                    # Add to value set checkbox
                    is_added = any(c["code"] == ui for c in st.session_state["value_set"])
                    if st.checkbox("", key=f"add_{ui}", value=is_added, label_visibility="collapsed"):
                        if not is_added:
                            st.session_state["value_set"].append({
                                "code": ui,
                                "name": name,
                                "vocab": source
                            })
                            st.rerun()
                    elif is_added:
                        st.session_state["value_set"] = [
                            c for c in st.session_state["value_set"] if c["code"] != ui
                        ]
                        st.rerun()
                
                with col_b:
                    st.markdown(f"**{name}**  \n`{ui}` • {source}")
                
                with col_c:
                    if st.button("🔍", key=f"explore_{ui}", help="Explore hierarchy"):
                        st.session_state["current_code"] = ui
                        st.session_state["current_vocab"] = source
                        st.session_state["current_name"] = name
                        st.rerun()
        
        # Tree navigation (when exploring a concept)
        if st.session_state.get("current_code"):
            st.markdown("---")
            st.markdown("### 🌳 Hierarchy Navigator")
            
            current_code = st.session_state["current_code"]
            current_vocab = st.session_state["current_vocab"]
            current_name = st.session_state.get("current_name", current_code)
            
            # Current concept with add button
            col_a, col_b, col_c = st.columns([1, 5, 1])
            with col_a:
                is_added = any(c["code"] == current_code for c in st.session_state["value_set"])
                if st.checkbox("", key=f"add_current_{current_code}", value=is_added, label_visibility="collapsed"):
                    if not is_added:
                        st.session_state["value_set"].append({
                            "code": current_code,
                            "name": current_name,
                            "vocab": current_vocab
                        })
                        st.rerun()
                elif is_added:
                    st.session_state["value_set"] = [
                        c for c in st.session_state["value_set"] if c["code"] != current_code
                    ]
                    st.rerun()
            with col_b:
                st.markdown(f"**Current:** {current_name}  \n`{current_code}`")
            with col_c:
                if st.button("← Back", key="back_to_search"):
                    st.session_state["current_code"] = None
                    st.rerun()
            
            # Fetch parents/children
            col1, col2 = st.columns(2)
            with col1:
                if st.button("⬆️ Show Parents", use_container_width=True):
                    if not api_key_vs or not validate_api_key(api_key_vs):
                        st.error("Valid API key required")
                    else:
                        url = f"{UMLS_BASE}/content/current/source/{current_vocab}/{current_code}/parents"
                        params = {"apiKey": api_key_vs, "pageSize": 50}
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
                    if not api_key_vs or not validate_api_key(api_key_vs):
                        st.error("Valid API key required")
                    else:
                        url = f"{UMLS_BASE}/content/current/source/{current_vocab}/{current_code}/children"
                        params = {"apiKey": api_key_vs, "pageSize": 50}
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
            if st.session_state.get("parents"):
                st.markdown("**Parents (broader concepts):**")
                for p in st.session_state["parents"]:
                    ui = p.get("ui", "")
                    name = p.get("name", "Unknown")
                    col_a, col_b, col_c = st.columns([1, 5, 1])
                    
                    with col_a:
                        is_added = any(c["code"] == ui for c in st.session_state["value_set"])
                        if st.checkbox("", key=f"add_p_{ui}", value=is_added, label_visibility="collapsed"):
                            if not is_added:
                                st.session_state["value_set"].append({
                                    "code": ui,
                                    "name": name,
                                    "vocab": current_vocab
                                })
                                st.rerun()
                        elif is_added:
                            st.session_state["value_set"] = [
                                c for c in st.session_state["value_set"] if c["code"] != ui
                            ]
                            st.rerun()
                    
                    with col_b:
                        st.markdown(f"↑ {name} `{ui}`")
                    
                    with col_c:
                        if st.button("→", key=f"nav_p_{ui}"):
                            st.session_state["current_code"] = ui
                            st.session_state["current_name"] = name
                            st.rerun()
            
            # Display children
            if st.session_state.get("children"):
                st.markdown("**Children (narrower concepts):**")
                for c in st.session_state["children"]:
                    ui = c.get("ui", "")
                    name = c.get("name", "Unknown")
                    col_a, col_b, col_c = st.columns([1, 5, 1])
                    
                    with col_a:
                        is_added = any(x["code"] == ui for x in st.session_state["value_set"])
                        if st.checkbox("", key=f"add_c_{ui}", value=is_added, label_visibility="collapsed"):
                            if not is_added:
                                st.session_state["value_set"].append({
                                    "code": ui,
                                    "name": name,
                                    "vocab": current_vocab
                                })
                                st.rerun()
                        elif is_added:
                            st.session_state["value_set"] = [
                                x for x in st.session_state["value_set"] if x["code"] != ui
                            ]
                            st.rerun()
                    
                    with col_b:
                        st.markdown(f"↓ {name} `{ui}`")
                    
                    with col_c:
                        if st.button("→", key=f"nav_c_{ui}"):
                            st.session_state["current_code"] = ui
                            st.session_state["current_name"] = name
                            st.rerun()
    
    # Right column - Your Value Set
    with col2:
        st.markdown("### 📋 Your Value Set")
        
        value_set = st.session_state["value_set"]
        
        if value_set:
            vs_display_name = st.session_state.get("vs_name", "Untitled Value Set")
            st.markdown(f"**{vs_display_name}**")
            st.caption(f"{len(value_set)} concept{'s' if len(value_set) != 1 else ''} added")
            
            # Show concepts
            for i, item in enumerate(value_set):
                col_a, col_b = st.columns([5, 1])
                with col_a:
                    st.markdown(f"""
                    <div style="font-size: 0.85rem; padding: 0.25rem 0; border-bottom: 1px solid #d1fae5;">
                        <strong>{item['name'][:50]}{'...' if len(item['name']) > 50 else ''}</strong><br>
                        <code style="font-size: 0.75rem; color: #059669;">{item['code']}</code>
                    </div>
                    """, unsafe_allow_html=True)
                with col_b:
                    if st.button("✕", key=f"rm_{i}"):
                        st.session_state["value_set"].pop(i)
                        st.rerun()
            
            st.markdown("---")
            
            # Export
            if st.button("Clear All", use_container_width=True):
                st.session_state["value_set"] = []
                st.rerun()
            
            vs_df = pd.DataFrame(value_set)
            csv = vs_df.to_csv(index=False)
            
            filename = vs_display_name.lower().replace(" ", "_") if vs_display_name else "value_set"
            filename = "".join(c for c in filename if c.isalnum() or c == "_")  # sanitize
            
            st.download_button(
                label="⬇ Download Value Set (CSV)",
                data=csv,
                file_name=f"{filename}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.info("No concepts added yet. Search and explore to build your value set.")
            
            # Example
            with st.expander("💡 Example: Building an Antibiotics value set"):
                st.markdown("""
                1. Enter "amoxicillin" in search
                2. Check concepts to add them
                3. Click 🔍 to explore hierarchy
                4. Navigate to parent "Penicillins"
                5. Show children to see related antibiotics
                6. Add all relevant drugs
                7. Name it "Antibiotics Value Set"
                8. Download CSV
                """)

