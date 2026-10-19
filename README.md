# EdgeWise — Intelligent Infrastructure Placement Advisor

EdgeWise compares application requirements with On Device, Far Edge, Regional Edge, and Cloud infrastructure. Its deterministic decision engine checks hard constraints before it calculates a transparent suitability score. An unknown capability remains unknown; it is never converted to zero.

## Start the app

From this folder in PowerShell:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

Open the local address printed by Streamlit. The Home page starts with no fabricated assessment. Save requirements and infrastructure data, run an assessment, and then review the results and explanation.

## Run checks

```powershell
py -m pytest
```

## Data and scoring

The default requirements and four infrastructure profiles are illustrative. They are not live provider measurements or quotes. Custom profile imports must use the exact four tier identifiers and supported capability fields; capability values may be `null` or omitted when unknown.

Only confirmed feasible tiers receive a score. Scores use the approved weights: latency 25%, data residency 20%, compute 20%, bandwidth 15%, and monthly cost 20%. The score is a suitability comparison, not a probability. Exact score ties follow canonical tier order: `on_device`, `far_edge`, `regional_edge`, `cloud`.

`decision_engine.py` has no AI dependency. `ai_explainer.py` creates a local explanation from the structured result and does not alter the recommendation.
