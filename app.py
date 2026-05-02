"""
UMLS Terminology Toolkit
Tab 1: Crosswalk — Upload CSV → map to any vocabulary → download
Tab 2: Value Set Builder — Search concepts → navigate tree → build value sets
"""

import streamlit as st
import pandas as pd
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="UMLS Toolkit", page_icon="🧬", layout="wide")

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .hero-banner {
        background: linear-gradient(135deg, #064e3b 0%, #047857 50%, #059669 100%);
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.5rem;
    }
    .hero-banner h1 { color: #ecfdf5; font-size: 1.5rem; margin: 0; }
    .hero-banner p { color: #a7f3d0; font-size: 0.85rem; margin: 0; }
    .step-header { display: flex; align-items: center; gap: 0.75rem; margin: 1rem 0 0.5rem; }
    .step-number {
        background: #047857; color: white; width: 32px; height: 32px;
        border-radius: 50%; display: flex; align-items: center; justify-content: center;
        font-weight: 700;
    }
    .step-title { font-size: 1.1rem; font-weight: 600; color: #064e3b; }
    .info-box {
        background: #ecfdf5; border-left: 4px solid #10b981;
        padding: 1rem; border-radius: 0 8px 8px 0; margin: 1rem 0;
    }
    .metric-card {
        flex: 1; background: #f0fdf4; border: 1px solid #d1fae5;
        border-radius: 12px; padding: 1.2rem; text-align: center;
    }
    .metric-row { display: flex; gap: 1rem; margin: 1rem 0; }
    .metric-card .value { font-size: 1.8rem; font-weight: 700; color: #064e3b; }
    .metric-card .label { font-size: 0.8rem; color: #059669; text-transform: uppercase; }
    .disclaimer {
        background: #fffbeb; border: 1px solid #fde68a;
        border-radius: 8px; padding: 0.75rem; font-size: 0.85rem; color: #92400e;
    }
</style>
""", unsafe_allow_html=True)

VOCAB_OPTIONS = {
    "ICD-10-CM": "ICD10CM",
    "ICD-10-PCS": "ICD10PCS",
    "ICD-9-CM": "ICD9CM",
    "SNOMED CT (US Edition)": "SNOMEDCT_US",
    "SNOMED CT (International)": "SNOMEDCT",
    "CPT": "CPT",
    "HCPCS": "HCPCS",
    "LOINC": "LNC",
    "RxNorm": "RXNORM",
    "MeSH": "MSH",
    "NCI Thesaurus": "NCI",
    "HPO": "HPO",
    "OMIM": "OMIM",
    "NDC": "NDC",
    "CVX": "CVX",
    "MedDRA": "MDR",
}

UMLS_BASE = "https://uts-ws.nlm.nih.gov/rest"


def crosswalk_code(api_key, source_vocab, code, target_vocab):
    url = f"{UMLS_BASE}/crosswalk/current/source/{source_vocab}/{code}"
    params = {"apiKey": api_key, "targetSource": target_vocab, "pageSize": 25}
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 401:
            return {"error": "Invalid API key"}
        if resp.status_code == 404:
            return {"error": "Code not found"}
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}
        data = resp.json()
        results = data.get("result", [])
        if not results:
            return {"error": "No mapping found"}
        return {"results": [
            {
                "target_code": r.get("ui", ""),
                "target_name": r.get("name", ""),
                "target_vocab": r.get("rootSource", target_vocab),
                "obsolete": r.get("obsolete", False),
            } for r in results
        ]}
    except Exception as e:
        return {"error": str(e)}


def validate_api_key(api_key):
    try:
        resp = requests.get(
            f"{UMLS_BASE}/content/current/CUI/C0009044",
            params={"apiKey": api_key},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception:
        return False


def process_batch(api_key, source_vocab, target_vocab, codes, progress_bar):
    results = [None] * len(codes)
    completed = 0
    total = len(codes)

    def do_one(idx, code):
        return idx, crosswalk_code(api_key, source_vocab, str(code).strip(), target_vocab)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(do_one, i, c): i for i, c in enumerate(codes)}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result
            completed += 1
            progress_bar.progress(completed / total, text=f"Processing {completed}/{total}…")
    return results


def search_concepts(api_key, term, vocab):
    url = f"{UMLS_BASE}/search/current"
    params = {"apiKey": api_key, "string": term, "sabs": vocab,
              "returnIdType": "code", "pageSize": 20}
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"
        return resp.json().get("result", {}).get("results", []), None
    except Exception as e:
        return None, str(e)


def get_relations(api_key, vocab, code, kind):
    url = f"{UMLS_BASE}/content/current/source/{vocab}/{code}/{kind}"
    params = {"apiKey": api_key, "pageSize": 50}
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("result", [])
        return []
    except Exception:
        return []


# ── UI ───────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-banner">
    <h1>🧬 UMLS Terminology Toolkit</h1>
    <p>Code crosswalking • Value set builder • Powered by NLM UMLS API</p>
</div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🔀 Crosswalk", "📋 Value Set Builder"])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: CROSSWALK
# ═══════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="step-header"><div class="step-number">1</div><div class="step-title">Enter API Key</div></div>', unsafe_allow_html=True)

    api_key = st.text_input(
        "UMLS API Key",
        type="password",
        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        key="cw_api",
    )
    if not api_key:
        st.info("👆 Enter your UMLS API key to run crosswalks. [Get one free here →](https://uts.nlm.nih.gov/uts/profile)")

    st.markdown('<div class="step-header"><div class="step-number">2</div><div class="step-title">Select Source & Target Vocabularies</div></div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        src_label = st.selectbox("Source Vocabulary", list(VOCAB_OPTIONS.keys()), key="cw_src")
        source_vocab = VOCAB_OPTIONS[src_label]
    with c2:
        tgt_options = {k: v for k, v in VOCAB_OPTIONS.items() if v != source_vocab}
        default_idx = list(tgt_options.keys()).index("SNOMED CT (US Edition)") if "SNOMED CT (US Edition)" in tgt_options else 0
        tgt_label = st.selectbox("Target Vocabulary", list(tgt_options.keys()), index=default_idx, key="cw_tgt")
        target_vocab = tgt_options[tgt_label]

    st.markdown(f"**Mapping:** `{source_vocab}` → `{target_vocab}`")

    st.markdown('<div class="step-header"><div class="step-number">3</div><div class="step-title">Upload CSV</div></div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Choose a CSV file containing your codes", type=["csv"])

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)

            st.markdown('<div class="step-header"><div class="step-number">4</div><div class="step-title">Select Code Column</div></div>', unsafe_allow_html=True)

            cc1, cc2 = st.columns([2, 1])
            with cc1:
                code_column = st.selectbox("Which column contains the source codes?", df.columns.tolist())
            with cc2:
                st.metric("Unique codes", f"{df[code_column].dropna().nunique():,}")

            samples = df[code_column].dropna().unique()[:3]
            st.caption(f"Sample codes: `{'`, `'.join(str(s) for s in samples)}`")

            st.markdown('<div class="step-header"><div class="step-number">5</div><div class="step-title">Run Crosswalk</div></div>', unsafe_allow_html=True)
            st.markdown('<div class="disclaimer">⚠️ <strong>Disclaimer:</strong> UMLS crosswalk mappings are based on CUI synonymy and have not been rigorously tested in clinical care. Review results before use in production.</div>', unsafe_allow_html=True)

            if st.button("🚀 Start Crosswalk", type="primary", use_container_width=True):
                if not api_key:
                    st.error("❌ Please enter your UMLS API key in Step 1")
                else:
                    with st.spinner("Validating API key..."):
                        if not validate_api_key(api_key):
                            st.error("❌ Invalid API key. Please check your UTS profile.")
                        else:
                            st.success("✅ API key valid - starting crosswalk...")
                            codes = df[code_column].astype(str).tolist()
                            unique_list = list(dict.fromkeys(codes))

                            progress_bar = st.progress(0, text="Starting…")
                            start = time.time()
                            raw = process_batch(api_key, source_vocab, target_vocab, unique_list, progress_bar)
                            elapsed = time.time() - start
                            progress_bar.progress(1.0, text="Complete!")

                            lookup = dict(zip(unique_list, raw))
                            out_rows = []
                            mapped = unmapped = multi = 0

                            for _, row in df.iterrows():
                                code = str(row[code_column]).strip()
                                result = lookup.get(code, {"error": "Not processed"})
                                if "results" in result and result["results"]:
                                    if len(result["results"]) > 1:
                                        multi += 1
                                    mapped += 1
                                    for m in result["results"]:
                                        r = row.to_dict()
                                        r["target_code"] = m["target_code"]
                                        r["target_name"] = m["target_name"]
                                        r["target_vocabulary"] = m["target_vocab"]
                                        r["mapping_status"] = "mapped"
                                        r["is_obsolete"] = m["obsolete"]
                                        out_rows.append(r)
                                else:
                                    unmapped += 1
                                    r = row.to_dict()
                                    r["target_code"] = ""
                                    r["target_name"] = ""
                                    r["target_vocabulary"] = target_vocab
                                    r["mapping_status"] = result.get("error", "unmapped")
                                    r["is_obsolete"] = False
                                    out_rows.append(r)

                            st.session_state["cw_result"] = pd.DataFrame(out_rows)
                            st.session_state["cw_stats"] = {
                                "mapped": mapped, "unmapped": unmapped, "multi": multi,
                                "total": len(codes), "unique": len(unique_list),
                                "elapsed": elapsed, "rows": len(out_rows),
                            }

            if "cw_result" in st.session_state:
                result_df = st.session_state["cw_result"]
                stats = st.session_state["cw_stats"]
                rate = (stats["mapped"] / stats["unique"] * 100) if stats["unique"] else 0

                st.markdown("---")
                st.markdown("### 📊 Crosswalk Complete!")
                st.markdown(f"""
                <div class="metric-row">
                    <div class="metric-card"><div class="value">{stats['unique']:,}</div><div class="label">Unique</div></div>
                    <div class="metric-card"><div class="value">{stats['mapped']:,}</div><div class="label">Mapped</div></div>
                    <div class="metric-card"><div class="value">{stats['unmapped']:,}</div><div class="label">Unmapped</div></div>
                    <div class="metric-card"><div class="value">{rate:.1f}%</div><div class="label">Map Rate</div></div>
                    <div class="metric-card"><div class="value">{stats['elapsed']:.1f}s</div><div class="label">Elapsed</div></div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("#### 👁 Preview Results")
                st.dataframe(result_df.head(100), use_container_width=True, height=250)
                st.caption(f"Showing first 100 of {len(result_df):,} rows")

                st.markdown("### 📥 Download Results")
                d1, d2, d3 = st.columns(3)
                d1.download_button("⬇ All Results", result_df.to_csv(index=False),
                                   file_name=f"crosswalk_{source_vocab}_to_{target_vocab}.csv",
                                   mime="text/csv", use_container_width=True)
                d2.download_button("⬇ Mapped Only",
                                   result_df[result_df["mapping_status"] == "mapped"].to_csv(index=False),
                                   file_name="crosswalk_mapped.csv",
                                   mime="text/csv", use_container_width=True)
                d3.download_button("⬇ Unmapped Only",
                                   result_df[result_df["mapping_status"] != "mapped"].to_csv(index=False),
                                   file_name="crosswalk_unmapped.csv",
                                   mime="text/csv", use_container_width=True)
        except Exception as e:
            st.error(f"Could not parse CSV: {e}")
    else:
        st.info("👆 Upload a CSV file with a column of medical codes")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: VALUE SET BUILDER
# ═══════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="info-box">Build custom value sets by searching concepts and navigating hierarchies. Perfect for creating cohorts, inclusion criteria, or standardized code lists.</div>', unsafe_allow_html=True)

    # Initialize all session state
    for key, default in [
        ("vs_concepts", []),
        ("vs_search_results", []),
        ("vs_explore_code", None),
        ("vs_explore_vocab", None),
        ("vs_explore_name", None),
        ("vs_parents", []),
        ("vs_children", []),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Step 1: API Key
    st.markdown('<div class="step-header"><div class="step-number">1</div><div class="step-title">Enter API Key</div></div>', unsafe_allow_html=True)
    vs_api_key = st.text_input(
        "UMLS API Key",
        type="password",
        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        key="vs_api",
    )
    if not vs_api_key:
        st.info("👆 Enter your UMLS API key to search and build value sets. [Get one free here →](https://uts.nlm.nih.gov/uts/profile)")

    # Step 2: Name
    st.markdown('<div class="step-header"><div class="step-number">2</div><div class="step-title">Name Your Value Set</div></div>', unsafe_allow_html=True)
    vs_name = st.text_input(
        "Value Set Name",
        placeholder="e.g., Antibiotics, Diabetes Diagnoses, Cardiac Procedures",
        key="vs_name",
    )

    # Step 3: Search
    st.markdown('<div class="step-header"><div class="step-number">3</div><div class="step-title">Search & Add Concepts</div></div>', unsafe_allow_html=True)

    sc1, sc2 = st.columns([1, 2])
    with sc1:
        vs_vocab_label = st.selectbox(
            "Vocabulary",
            list(VOCAB_OPTIONS.keys()),
            index=list(VOCAB_OPTIONS.keys()).index("SNOMED CT (US Edition)"),
            key="vs_vocab_select",
        )
        vs_vocab = VOCAB_OPTIONS[vs_vocab_label]
    with sc2:
        vs_search_term = st.text_input(
            "Search for a concept",
            placeholder="e.g., amoxicillin, type 2 diabetes",
            key="vs_search_term",
        )

    if st.button("🔎 Search", type="primary", key="vs_search_btn"):
        if not vs_api_key:
            st.error("❌ Please enter your API key in Step 1")
        elif not vs_search_term:
            st.warning("Please enter a search term")
        else:
            with st.spinner("Searching UMLS…"):
                results, err = search_concepts(vs_api_key, vs_search_term, vs_vocab)
                if err:
                    st.error(f"Search failed: {err}")
                elif not results:
                    st.info("No results found")
                    st.session_state["vs_search_results"] = []
                else:
                    st.session_state["vs_search_results"] = results
                    st.session_state["vs_explore_code"] = None

    # Show search results
    if st.session_state["vs_search_results"] and not st.session_state["vs_explore_code"]:
        st.markdown(f"**Found {len(st.session_state['vs_search_results'])} concepts:**")

        for r in st.session_state["vs_search_results"]:
            ui = r.get("ui", "")
            name = r.get("name", "Unknown")
            source = r.get("rootSource", vs_vocab)
            already_in = any(c["code"] == ui for c in st.session_state["vs_concepts"])

            rc1, rc2, rc3 = st.columns([1, 6, 1])
            with rc1:
                checked = st.checkbox("Add", key=f"sr_chk_{ui}", value=already_in, label_visibility="collapsed")
                if checked and not already_in:
                    st.session_state["vs_concepts"].append({"code": ui, "name": name, "vocab": source})
                    st.rerun()
                elif not checked and already_in:
                    st.session_state["vs_concepts"] = [c for c in st.session_state["vs_concepts"] if c["code"] != ui]
                    st.rerun()
            with rc2:
                st.markdown(f"**{name}**  \n`{ui}` • {source}")
            with rc3:
                if st.button("🔍", key=f"sr_explore_{ui}", help="Explore hierarchy"):
                    st.session_state["vs_explore_code"] = ui
                    st.session_state["vs_explore_vocab"] = source
                    st.session_state["vs_explore_name"] = name
                    st.session_state["vs_parents"] = []
                    st.session_state["vs_children"] = []
                    st.rerun()

    # Tree navigator
    if st.session_state["vs_explore_code"]:
        st.markdown("---")
        st.markdown("### 🌳 Hierarchy Navigator")

        ec = st.session_state["vs_explore_code"]
        ev = st.session_state["vs_explore_vocab"]
        en = st.session_state["vs_explore_name"]

        st.markdown(f"**Current concept:** {en} `{ec}`")
        in_set = any(c["code"] == ec for c in st.session_state["vs_concepts"])

        bc1, bc2 = st.columns(2)
        with bc1:
            if not in_set:
                if st.button("➕ Add to value set", key=f"add_curr_{ec}"):
                    st.session_state["vs_concepts"].append({"code": ec, "name": en, "vocab": ev})
                    st.rerun()
            else:
                st.success("✓ Already in value set")
        with bc2:
            if st.button("← Back to search", key="vs_back"):
                st.session_state["vs_explore_code"] = None
                st.rerun()

        nc1, nc2 = st.columns(2)
        with nc1:
            if st.button("⬆️ Show Parents", key="vs_parents_btn", use_container_width=True):
                st.session_state["vs_parents"] = get_relations(vs_api_key, ev, ec, "parents")
        with nc2:
            if st.button("⬇️ Show Children", key="vs_children_btn", use_container_width=True):
                st.session_state["vs_children"] = get_relations(vs_api_key, ev, ec, "children")

        if st.session_state["vs_parents"]:
            st.markdown("**Parents (broader):**")
            for p in st.session_state["vs_parents"]:
                ui = p.get("ui", "")
                name = p.get("name", "Unknown")
                already = any(c["code"] == ui for c in st.session_state["vs_concepts"])

                pc1, pc2, pc3 = st.columns([1, 6, 1])
                with pc1:
                    chk = st.checkbox("Add", key=f"par_chk_{ui}", value=already, label_visibility="collapsed")
                    if chk and not already:
                        st.session_state["vs_concepts"].append({"code": ui, "name": name, "vocab": ev})
                        st.rerun()
                    elif not chk and already:
                        st.session_state["vs_concepts"] = [c for c in st.session_state["vs_concepts"] if c["code"] != ui]
                        st.rerun()
                with pc2:
                    st.markdown(f"↑ {name} `{ui}`")
                with pc3:
                    if st.button("→", key=f"par_nav_{ui}"):
                        st.session_state["vs_explore_code"] = ui
                        st.session_state["vs_explore_name"] = name
                        st.session_state["vs_parents"] = []
                        st.session_state["vs_children"] = []
                        st.rerun()

        if st.session_state["vs_children"]:
            st.markdown("**Children (narrower):**")
            for ch in st.session_state["vs_children"]:
                ui = ch.get("ui", "")
                name = ch.get("name", "Unknown")
                already = any(c["code"] == ui for c in st.session_state["vs_concepts"])

                cc1, cc2, cc3 = st.columns([1, 6, 1])
                with cc1:
                    chk = st.checkbox("Add", key=f"chi_chk_{ui}", value=already, label_visibility="collapsed")
                    if chk and not already:
                        st.session_state["vs_concepts"].append({"code": ui, "name": name, "vocab": ev})
                        st.rerun()
                    elif not chk and already:
                        st.session_state["vs_concepts"] = [c for c in st.session_state["vs_concepts"] if c["code"] != ui]
                        st.rerun()
                with cc2:
                    st.markdown(f"↓ {name} `{ui}`")
                with cc3:
                    if st.button("→", key=f"chi_nav_{ui}"):
                        st.session_state["vs_explore_code"] = ui
                        st.session_state["vs_explore_name"] = name
                        st.session_state["vs_parents"] = []
                        st.session_state["vs_children"] = []
                        st.rerun()

    # Your Value Set (full width below)
    st.markdown("---")
    st.markdown("### 📋 Your Value Set")

    if st.session_state["vs_concepts"]:
        display_name = vs_name or "Untitled Value Set"
        st.markdown(f"**{display_name}** — {len(st.session_state['vs_concepts'])} concepts")

        vs_df = pd.DataFrame(st.session_state["vs_concepts"])
        st.dataframe(vs_df, use_container_width=True, hide_index=True)

        dl1, dl2 = st.columns([3, 1])
        with dl1:
            fname = display_name.lower().replace(" ", "_")
            fname = "".join(c for c in fname if c.isalnum() or c == "_") or "value_set"
            st.download_button(
                f"⬇ Download {display_name} (CSV)",
                vs_df.to_csv(index=False),
                file_name=f"{fname}.csv",
                mime="text/csv",
                use_container_width=True,
                key="vs_download",
            )
        with dl2:
            if st.button("🗑 Clear All", use_container_width=True, key="vs_clear"):
                st.session_state["vs_concepts"] = []
                st.rerun()
    else:
        st.info("No concepts added yet. Search above and check the boxes to build your value set.")
        with st.expander("💡 Example: Building an Antibiotics value set"):
            st.markdown("""
            1. Name it "Antibiotics"
            2. Search for "amoxicillin"
            3. Check concepts to add them
            4. Click 🔍 to explore hierarchy
            5. Show Parents/Children to find related drugs
            6. Add all relevant drugs
            7. Download CSV
            """)
