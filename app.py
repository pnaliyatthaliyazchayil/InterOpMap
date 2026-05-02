"""
UMLS Crosswalk Tool — Streamlit UI
Upload a CSV of source codes, pick source & target vocabularies,
and get back a mapped CSV powered by the UMLS REST API.
"""

import streamlit as st
import pandas as pd
import requests
import time
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="UMLS Crosswalk Tool",
    page_icon="🔀",
    layout="wide",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

    /* Global */
    .stApp {
        font-family: 'IBM Plex Sans', sans-serif;
    }
    
    /* Header banner */
    .hero-banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0c4a6e 100%);
        border-radius: 16px;
        padding: 2.5rem 2rem;
        margin-bottom: 2rem;
        border: 1px solid rgba(56, 189, 248, 0.2);
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
        background: radial-gradient(circle, rgba(56,189,248,0.08) 0%, transparent 70%);
        border-radius: 50%;
    }
    .hero-banner h1 {
        color: #f0f9ff;
        font-size: 2rem;
        font-weight: 700;
        margin: 0 0 0.5rem 0;
        letter-spacing: -0.5px;
    }
    .hero-banner p {
        color: #7dd3fc;
        font-size: 1rem;
        margin: 0;
        font-weight: 400;
    }

    /* Metric cards */
    .metric-row {
        display: flex;
        gap: 1rem;
        margin: 1rem 0;
    }
    .metric-card {
        flex: 1;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
    }
    .metric-card .value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0f172a;
        font-family: 'IBM Plex Mono', monospace;
    }
    .metric-card .label {
        font-size: 0.8rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 0.25rem;
    }

    /* Status badges */
    .badge-success {
        display: inline-block;
        background: #dcfce7;
        color: #166534;
        padding: 0.2rem 0.6rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-warning {
        display: inline-block;
        background: #fef3c7;
        color: #92400e;
        padding: 0.2rem 0.6rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-error {
        display: inline-block;
        background: #fee2e2;
        color: #991b1b;
        padding: 0.2rem 0.6rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* Step indicators */
    .step-header {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 1rem;
    }
    .step-number {
        background: #0c4a6e;
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
        color: #0f172a;
    }

    /* Info box */
    .info-box {
        background: #f0f9ff;
        border-left: 4px solid #0ea5e9;
        padding: 1rem 1.25rem;
        border-radius: 0 8px 8px 0;
        margin: 1rem 0;
        font-size: 0.9rem;
        color: #0c4a6e;
    }

    /* Disclaimer */
    .disclaimer {
        background: #fffbeb;
        border: 1px solid #fde68a;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-size: 0.8rem;
        color: #92400e;
        margin: 1rem 0;
    }

    /* Hide default streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Style the file uploader */
    [data-testid="stFileUploader"] {
        border: 2px dashed #cbd5e1;
        border-radius: 12px;
        padding: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ── UMLS vocabulary abbreviations ────────────────────────────────────────────
# Commonly used source vocabularies in UMLS crosswalks
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

# ── API helper ───────────────────────────────────────────────────────────────
UMLS_BASE = "https://uts-ws.nlm.nih.gov/rest"

def crosswalk_code(api_key: str, source_vocab: str, code: str, target_vocab: str):
    """
    Call the UMLS crosswalk endpoint for a single code.
    Returns a list of dicts with target code info, or an error dict.
    """
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
    """
    Process a list of codes through the crosswalk API.
    Uses a thread pool for parallelism but respects rate limits.
    Returns a list of result dicts aligned with input codes.
    """
    results = [None] * len(codes)
    completed = 0
    total = len(codes)
    
    # Use modest concurrency to avoid rate-limiting
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
                f"<span style='font-family: IBM Plex Mono; font-size: 0.85rem; color: #64748b;'>"
                f"Latest: code #{idx+1} — "
                f"{'✅ mapped' if 'results' in result else '⚠️ ' + result.get('error', 'unknown')}"
                f"</span>",
                unsafe_allow_html=True
            )
            # Small delay between completions to be polite to the API
            time.sleep(0.05)
    
    return results


# ── UI ───────────────────────────────────────────────────────────────────────

# Hero banner
st.markdown("""
<div class="hero-banner">
    <h1>🔀 UMLS Crosswalk Tool</h1>
    <p>Upload a CSV of medical codes → map them to any UMLS vocabulary → download results</p>
</div>
""", unsafe_allow_html=True)

# Sidebar — API key & vocab config
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
    # Remove source from target options
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
        "<div style='font-size:0.75rem; color:#94a3b8;'>"
        "Powered by NLM UMLS REST API<br>"
        "Free license at <a href='https://uts.nlm.nih.gov' target='_blank'>uts.nlm.nih.gov</a>"
        "</div>",
        unsafe_allow_html=True
    )

# ── Main content ─────────────────────────────────────────────────────────────

# Step 1: Upload
st.markdown("""
<div class="step-header">
    <div class="step-number">1</div>
    <div class="step-title">Upload Your CSV</div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="info-box">
    Upload a CSV containing a column of medical codes (e.g., ICD-10 diagnosis codes).
    You'll pick which column holds the codes in the next step.
    Optional columns like patient ID, description, etc. will be preserved in the output.
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
    
    # Step 2: Configure columns
    st.markdown("""
    <div class="step-header">
        <div class="step-number">2</div>
        <div class="step-title">Configure Columns</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        code_column = st.selectbox(
            "Which column contains the source codes?",
            options=df.columns.tolist(),
            help="Select the column that holds ICD, SNOMED, LOINC (etc.) codes"
        )
    with col2:
        st.markdown(f"**Mapping direction:**")
        st.markdown(
            f"`{source_vocab}` → `{target_vocab}`"
        )
        unique_codes = df[code_column].dropna().nunique()
        st.markdown(f"Unique codes to map: **{unique_codes:,}**")
    
    # Show sample codes
    sample_codes = df[code_column].dropna().unique()[:5]
    st.markdown(f"Sample codes: `{'`, `'.join(str(c) for c in sample_codes)}`")
    
    # Disclaimer
    st.markdown("""
    <div class="disclaimer">
        ⚠️ <strong>Important:</strong> UMLS crosswalk mappings are based on CUI synonymy and have 
        <em>not been rigorously tested in clinical care</em>. Results should be reviewed by a qualified 
        coding professional before use in billing, clinical, or regulatory workflows.
    </div>
    """, unsafe_allow_html=True)
    
    # Step 3: Run
    st.markdown("""
    <div class="step-header">
        <div class="step-number">3</div>
        <div class="step-title">Run Crosswalk</div>
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
        
        # De-duplicate for API efficiency, then map back
        unique_list = list(dict.fromkeys(codes))  # preserves order
        
        st.markdown(f"Processing **{len(unique_list):,}** unique codes "
                     f"({len(codes):,} total rows)…")
        
        progress_bar = st.progress(0, text="Starting…")
        status_text = st.empty()
        
        start_time = time.time()
        raw_results = process_batch(
            api_key, source_vocab, target_vocab,
            unique_list, progress_bar, status_text
        )
        elapsed = time.time() - start_time
        
        progress_bar.progress(1.0, text="Complete!")
        
        # Build lookup from unique codes to results
        lookup = dict(zip(unique_list, raw_results))
        
        # Build output dataframe
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
                # One row per mapping (1-to-many support)
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
        
        # Store in session state for persistence
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
    
    # Step 4: Results (persisted via session_state)
    if "result_df" in st.session_state:
        result_df = st.session_state["result_df"]
        stats = st.session_state["stats"]
        
        st.markdown("""
        <div class="step-header">
            <div class="step-number">4</div>
            <div class="step-title">Results & Export</div>
        </div>
        """, unsafe_allow_html=True)
        
        # Metrics
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
        
        # Tabs for viewing
        tab_all, tab_mapped, tab_unmapped = st.tabs(["All Results", "Mapped Only", "Unmapped Only"])
        
        with tab_all:
            st.dataframe(result_df, use_container_width=True, height=400)
        with tab_mapped:
            mapped_df = result_df[result_df["mapping_status"] == "mapped"]
            st.dataframe(mapped_df, use_container_width=True, height=400)
        with tab_unmapped:
            unmapped_df = result_df[result_df["mapping_status"] != "mapped"]
            st.dataframe(unmapped_df, use_container_width=True, height=400)
        
        # Export
        st.markdown("### 📥 Download Results")
        
        col_a, col_b, col_c = st.columns(3)
        
        # Full results
        csv_all = result_df.to_csv(index=False)
        col_a.download_button(
            label="⬇ All Results (CSV)",
            data=csv_all,
            file_name=f"crosswalk_{source_vocab}_to_{target_vocab}_all.csv",
            mime="text/csv",
            use_container_width=True,
        )
        
        # Mapped only
        csv_mapped = result_df[result_df["mapping_status"] == "mapped"].to_csv(index=False)
        col_b.download_button(
            label="⬇ Mapped Only (CSV)",
            data=csv_mapped,
            file_name=f"crosswalk_{source_vocab}_to_{target_vocab}_mapped.csv",
            mime="text/csv",
            use_container_width=True,
        )
        
        # Unmapped only
        csv_unmapped = result_df[result_df["mapping_status"] != "mapped"].to_csv(index=False)
        col_c.download_button(
            label="⬇ Unmapped Only (CSV)",
            data=csv_unmapped,
            file_name=f"crosswalk_{source_vocab}_to_{target_vocab}_unmapped.csv",
            mime="text/csv",
            use_container_width=True,
        )

else:
    # Empty state — show supported crosswalks
    st.markdown("### Supported Crosswalk Paths")
    st.markdown(
        "The UMLS Metathesaurus links **200+ vocabularies** via Concept Unique Identifiers (CUIs). "
        "Any pair of vocabularies that share CUIs can be crosswalked. Common paths include:"
    )
    
    paths = [
        ("ICD-9-CM", "→", "ICD-10-CM", "Diagnosis migration"),
        ("ICD-10-CM", "→", "SNOMED CT", "Clinical ↔ billing bridge"),
        ("SNOMED CT", "→", "ICD-10-CM", "EHR to claims"),
        ("CPT", "→", "SNOMED CT", "Procedure mapping"),
        ("LOINC", "→", "SNOMED CT", "Lab observation mapping"),
        ("RxNorm", "→", "NDC", "Drug code mapping"),
        ("MeSH", "→", "SNOMED CT", "Literature to clinical"),
        ("HPO", "→", "SNOMED CT", "Phenotype mapping"),
    ]
    
    path_df = pd.DataFrame(paths, columns=["Source", "", "Target", "Use Case"])
    st.dataframe(path_df, use_container_width=True, hide_index=True)
    
    st.markdown("""
    <div class="info-box">
        <strong>Getting started:</strong><br>
        1. Get a free UMLS API key at <a href="https://uts.nlm.nih.gov/uts/profile" target="_blank">uts.nlm.nih.gov</a><br>
        2. Enter it in the sidebar<br>
        3. Upload your CSV and configure the source code column<br>
        4. Pick your target vocabulary and click <strong>Start Crosswalk</strong>
    </div>
    """, unsafe_allow_html=True)
