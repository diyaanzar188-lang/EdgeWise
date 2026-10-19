# EdgeWise — Edge vs Cloud Placement Advisor

EdgeWise is a decision-support application for developers and architects choosing where an AI workload should run. It evaluates four deployment tiers against saved workload requirements and infrastructure capability data, then explains the resulting recommendation. It does not deploy workloads.

**Hackathon:** Infosys IGNITE ENG NEXT 2026 Hack-AI-Thon<br>
**Problem statement:** NC-03 — Edge vs Cloud Placement Advisor

## Problem statement and proposed solution

AI workloads have different latency, privacy, compute, bandwidth, and cost needs. EdgeWise compares those needs with available infrastructure data so teams can review feasible placement options and their trade-offs in one place. A deterministic decision engine performs all feasibility checks, scoring, ranking, and recommendation; optional Qualcomm Imagine AI text explains the already-computed result.

## Key features

- Compare **On Device**, **Far Edge**, **Regional Edge**, and **Cloud**.
- Set workload latency, onsite data residency, minimum compute, bandwidth, and monthly cost requirements.
- Use the illustrative profiles or enter infrastructure capabilities in the table or JSON input. Missing capability data can remain unknown.
- Review feasibility status and constraint evidence for each tier, score breakdowns, ranking, and feasible alternatives.
- Download an assessment JSON report.
- See a concise explanation from Qualcomm Imagine when configured and available, with a deterministic local explanation as fallback.
- Navigate through the requirements, infrastructure, assessment, results, and explanation workflow.

## How EdgeWise works

1. **Define requirements.** Enter the maximum latency, whether data must stay onsite, minimum compute, required bandwidth, and maximum monthly cost for the workload.
2. **Provide infrastructure data.** Use the built-in illustrative profiles or enter capability values for the four tiers. Unknown values may be left blank or set to `null`.
3. **Check hard constraints.** The decision engine evaluates latency, onsite residency when required, compute, bandwidth, and monthly cost. A known failure makes a tier infeasible. Missing or invalid capability data leaves a tier unverified unless another known failure already makes it infeasible.
4. **Score and rank feasible tiers.** Only tiers with confirmed feasibility receive a suitability score. The weighted factors are latency (25%), data residency (20%), compute (20%), bandwidth (15%), and monthly cost (20%). Tiers are ranked by score; exact ties follow the fixed order On Device, Far Edge, Regional Edge, Cloud. The top-ranked feasible tier is recommended. If no tier is confirmed feasible, there is no recommendation.
5. **Review the result.** The app shows status and constraint evidence, score details, ranking, alternatives, and a downloadable JSON report.
6. **Read the explanation.** If Qualcomm Imagine is configured, EdgeWise asks the model for concise prose based on authoritative evidence from the assessment. If configuration, the request, or the response is unavailable or invalid, EdgeWise uses its deterministic explanation. The engine's result remains authoritative in either case; AI text cannot change feasibility, scores, ranking, or recommendation.

## Technology stack

Verified from the project files:

- Python
- Streamlit for the application UI
- Pandas for tabular comparison and score displays
- Python standard library for JSON handling and the Qualcomm Imagine HTTP request
- Pytest for automated tests

Package dependencies are listed in [`requirements.txt`](requirements.txt). The AI integration does not require a separate HTTP client or dotenv package.

## Project structure

```text
EdgeWise/
├── app.py                      # Streamlit UI and assessment workflow
├── ai_explainer.py             # Optional Qualcomm explanation and local fallback
├── contracts.py                # Typed assessment and infrastructure data contracts
├── decision_engine.py          # Input checks, feasibility, scoring, ranking, recommendation
├── infrastructure_data.py      # Requirement defaults, tier labels, demo profiles, validation
├── requirements.txt            # Runtime and test dependencies
├── README.md
└── tests/
    ├── test_ai_explainer.py
    ├── test_app_workflow.py
    └── test_decision_engine.py
```

## Installation and local setup (Windows PowerShell)

From the project folder, create and activate a virtual environment, then install the listed dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks environment activation, run the app and tests using the virtual environment's Python executable directly, as shown below.

### Optional Qualcomm Imagine configuration

The AI explanation is optional. Set these environment variables to enable it:

- `QUALCOMM_IMAGINE_API_KEY` — your Qualcomm Imagine API key
- `QUALCOMM_IMAGINE_ENDPOINT` — the API base URL; for example, `https://aisuite.cirrascale.com/apis/v2`
- `QUALCOMM_IMAGINE_MODEL` — model name; the default in the code is `Llama-3.1-8B`

For the current PowerShell session, set them without putting credentials in source files:

```powershell
$env:QUALCOMM_IMAGINE_API_KEY = "<your API key>"
$env:QUALCOMM_IMAGINE_ENDPOINT = "https://aisuite.cirrascale.com/apis/v2"
$env:QUALCOMM_IMAGINE_MODEL = "Llama-3.1-8B"
```

The project also supports loading these names from a local `.env` file, and `.gitignore` excludes `.env`. Keep the file local and never commit credentials. No `.env.example` is present in this repository.

Without a usable API key and endpoint, or if the request or response fails validation, the app displays the deterministic fallback explanation.

## Run the Streamlit application

With the virtual environment active:

```powershell
python -m streamlit run app.py
```

Or run it without activating the environment:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local address printed by Streamlit. Start on Home, save requirements and infrastructure data, run the assessment, then review the results and explanation.

## Run automated tests

With the virtual environment active:

```powershell
python -m pytest -q
```

Or use its Python executable directly:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The AI integration tests use mocked HTTP responses and do not require an API key or a real API request.

## Current limitations

- The default workload requirements and infrastructure profiles are illustrative, not live measurements, provider quotes, or automatic discovery. Review or replace the capability data for your own scenario.
- The supported requirements are limited to the five fields listed above. **Criticality is not currently an input** to validation or scoring.
- Results are decision support. EdgeWise does not provision or deploy a workload.
- The Qualcomm explanation depends on a working endpoint, credentials, and a response that passes the implementation's checks. The deterministic explanation remains available when AI is unavailable.

## Team and event details

This README identifies the project and event supplied for the hackathon. Team member names and roles are not documented in the repository.
