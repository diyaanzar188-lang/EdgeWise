# EdgeWise — Intelligent Infrastructure Placement Advisor

EdgeWise compares application requirements with On Device, Far Edge, Regional Edge, and Cloud infrastructure. Its deterministic decision engine checks hard constraints before it calculates a transparent suitability score. An unknown capability remains unknown; it is never converted to zero.

## Start the app

From this folder in PowerShell:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

Open the local address printed by Streamlit. The Home page starts with no fabricated assessment. Save requirements and infrastructure data, run an assessment, and then review the results and explanation.

## Optional AI explanation

The current project does not include a Qualcomm SDK, a configured Qualcomm endpoint/model, or an API integration to verify. EdgeWise therefore uses the deterministic local explanation in `ai_explainer.py`; the placement assessment remains fully functional without credentials or network access. No API key is required or read by the current app. Add provider integration only after selecting the supported SDK and endpoint for your Qualcomm AI account, and keep any credential in an environment variable or a local `.env` file (which `.gitignore` excludes).

## Run checks

```powershell
py -m pytest
```

## Data and scoring

The default requirements and four infrastructure profiles are illustrative. They are not live provider measurements or quotes. Custom profile imports must use the exact four tier identifiers and supported capability fields; capability values may be `null` or omitted when unknown.

For `Specific Region Only`, custom profiles may include a `location` value. A match requires exact equality after trimming surrounding whitespace and ignoring case (for example, ` India ` matches `india`). Missing or blank locations remain unknown and never count as a match. Existing `data_must_stay_onsite` booleans migrate explicitly: `true` means `On-site Only` and `false` means `No Restriction`; exact legacy strings `Yes` and `No` are handled the same way. Other legacy values are rejected.

Only confirmed feasible tiers receive a score. Scores use the approved weights: latency 25%, data residency 20%, compute 20%, bandwidth 15%, and monthly cost 20%. The score is a suitability comparison, not a probability. Exact score ties follow canonical tier order: `on_device`, `far_edge`, `regional_edge`, `cloud`.

`decision_engine.py` has no AI dependency. `ai_explainer.py` creates a local explanation from the structured result and does not alter the recommendation.

## Troubleshooting

- If Streamlit reports a port conflict, stop the existing app or start another port with `py -m streamlit run app.py --server.port 8502`.
- If the app shows no recommendation, inspect the constraint evidence. A tier can be unverified when required capability information is missing or invalid; unknown values are not treated as zero.
- If custom profile input is rejected, use only the four tier keys and the five documented capability names. Numeric capabilities must be finite and nonnegative; compute must be `low`, `medium`, or `high`; onsite capability must be a boolean. Use `null` or omit a field for unknown information.
- The demonstration infrastructure values are illustrative and are not live provider measurements or quotes.
