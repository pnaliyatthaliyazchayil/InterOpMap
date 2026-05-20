# UMLS Crosswalk Tool

A Streamlit UI that lets small hospitals and health IT teams upload a CSV of medical codes and crosswalk them to any UMLS-supported vocabulary — no coding required.

Visit: https://interopmap.streamlit.app/

## What It Does

1. **Upload** a CSV containing patient records with source codes (ICD-9, ICD-10, SNOMED, LOINC, etc.)
2. **Configure** which column holds the codes, pick source & target vocabularies
3. **Process** — the tool calls the UMLS REST API `/crosswalk` endpoint for each code
4. **Download** the enriched CSV with mapped target codes, names, and mapping status

## Prerequisites

- **Python 3.9+**
- **UMLS API Key** — free from [uts.nlm.nih.gov](https://uts.nlm.nih.gov/uts/profile)
  - Sign up for a UMLS Terminology Services (UTS) account
  - Accept the UMLS license agreement
  - Copy your API key from your profile page

## Setup

```bash
# Clone or download this folder
cd umls_crosswalk

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Supported Vocabularies

The tool supports 20+ UMLS source vocabularies including:

| Abbreviation   | Vocabulary                          |
|----------------|-------------------------------------|
| ICD10CM        | ICD-10-CM (US Clinical Modification)|
| ICD9CM         | ICD-9-CM (Diagnoses)               |
| SNOMEDCT_US    | SNOMED CT (US Edition)             |
| CPT            | Current Procedural Terminology     |
| LNC            | LOINC (Lab Observations)           |
| RXNORM         | RxNorm (Drug Names)                |
| HCPCS          | Healthcare Common Procedure Codes  |
| MSH            | MeSH (Medical Subject Headings)    |
| NCI            | NCI Thesaurus                      |
| NDC            | National Drug Code                 |
| MDR            | MedDRA                             |
| HPO            | Human Phenotype Ontology           |
| CVX            | Vaccine Codes                      |

Any pair of vocabularies that share UMLS CUIs can be crosswalked.

## Sample Data

A `sample_data.csv` is included with 12 example codes (mix of ICD-10-CM and ICD-9-CM) for testing.

## How the Crosswalk Works

The UMLS Metathesaurus assigns a **Concept Unique Identifier (CUI)** to each distinct biomedical concept. When two codes from different vocabularies share the same CUI, they are considered synonymous. The `/crosswalk` API endpoint leverages this synonymy to return target codes.

```
ICD-10-CM: E11.9  →  CUI: C0011860  →  SNOMED CT: 44054006
(Type 2 DM)          (Diabetes)         (Type 2 DM)
```

## Important Disclaimers

- UMLS crosswalk mappings are based on CUI synonymy and have **not been rigorously tested in clinical care** (per NLM's own documentation).
- Results should be reviewed by a qualified coding professional before use in billing, clinical, or regulatory workflows.
- 1-to-many mappings are common — the tool expands these into separate rows.
- The API has rate limits. For large batches (>5,000 codes), consider running in smaller chunks.

## Architecture

```
┌──────────────┐     CSV Upload      ┌──────────────────┐
│   Hospital   │ ──────────────────► │   Streamlit UI   │
│   User       │                     │                  │
│              │ ◄────────────────── │  Column Config   │
│              │   Mapped CSV        │  Vocab Selector  │
└──────────────┘                     │  Progress Bar    │
                                     └───────┬──────────┘
                                             │
                                             │ REST API
                                             ▼
                                     ┌──────────────────┐
                                     │  UMLS REST API   │
                                     │  /crosswalk/     │
                                     │  current/source/ │
                                     └──────────────────┘
```
