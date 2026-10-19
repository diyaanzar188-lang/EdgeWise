"""EdgeWise — Intelligent Infrastructure Placement Advisor."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping

import pandas as pd
import streamlit as st

from ai_explainer import explain_assessment
from decision_engine import TIER_ORDER, evaluate_placement
from infrastructure_data import DEFAULT_REQUIREMENTS, TIER_LABELS, get_demo_profiles

st.set_page_config(page_title="EdgeWise | Placement Advisor", page_icon="◉", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root { color-scheme: dark; --bg:#111013; --side:#09090B; --card:#1C191F; --card2:#25212A; --pink:#D77BCB; --purple:#A96BC4; --text:#F7F4F8; --muted:#D0C7D5; --border:#38303D; --success:#47C9A5; --warning:#E7BD70; --error:#EF747C; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; color:var(--text); }
h1,h2,h3 { font-family:'Manrope',sans-serif; letter-spacing:-.035em; color:var(--text); }
.stApp { background:var(--bg); }
.block-container { max-width:1320px; padding-top:2rem; padding-bottom:4rem; }
.eyebrow { color:var(--pink); font-size:.73rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase; margin-bottom:.65rem; }
.hero { position:relative; isolation:isolate; overflow:hidden; text-align:center; background:radial-gradient(ellipse at 50% 0%,rgba(169,107,196,.16),transparent 55%),linear-gradient(145deg,#1C191F,#17141A); border:1px solid var(--border); border-radius:22px; padding:3.4rem 2rem 3rem; }
.hero:before { content:''; position:absolute; z-index:-1; width:420px;height:240px;top:-100px;left:calc(50% - 210px);background:rgba(215,123,203,.17);filter:blur(75px);border-radius:50%; }
.hero h1 { font-size:clamp(2.4rem,5.4vw,4.5rem); line-height:1.08; margin:.35rem 0 1rem; background:linear-gradient(135deg,#A96BC4,#E6A0D8);-webkit-background-clip:text;background-clip:text;color:transparent; }
.hero p { color:var(--muted); font-size:1.08rem; max-width:780px; margin:.7rem auto 0; line-height:1.7; }
.soft-card,.tier-card,.workflow-card { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:1.25rem 1.35rem; height:100%; transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease; }
.tier-card { min-height:224px; background:linear-gradient(155deg,#211B24,#19161D); border-color:#49344D; }
.tier-card:hover,.workflow-card:hover { transform:translateY(-3px); border-color:var(--pink); box-shadow:0 9px 28px rgba(169,107,196,.13); }
.card-number,.tier-name { color:var(--muted); font-size:.77rem; letter-spacing:.08em; }
.tier-icon { color:var(--pink); font-size:1.45rem; margin:.45rem 0; }
.tier-card h3 { margin:.15rem 0 .45rem; font-size:1.23rem; }
.tier-card p,.workflow-card p { color:var(--muted); line-height:1.55; font-size:.92rem; }
.badge { display:inline-block; margin-top:.4rem; color:#E6A0D8; font-size:.68rem; letter-spacing:.11em; font-weight:700; }
.workflow-card { min-height:178px; }
.workflow-card h3 { font-size:1.08rem; margin:.55rem 0 .3rem; }
.metric-value { font-family:'Manrope',sans-serif; font-size:1.45rem; font-weight:700; margin-top:.25rem; }
.muted, [data-testid="stCaptionContainer"] { color:var(--muted)!important; }
[data-testid="stSidebar"] { background:var(--side); border-right:1px solid var(--border); }
[data-testid="stSidebar"] * { color:var(--text); }
.stButton > button, .stDownloadButton > button { border-radius:10px; border:1px solid var(--border); color:var(--text); background:var(--card2); transition:transform .18s ease,border-color .18s ease; }
.stButton > button:hover,.stDownloadButton > button:hover { border-color:var(--pink); transform:translateY(-1px); color:var(--text); }
.stButton > button[kind="primary"],.stDownloadButton > button[kind="primary"] { background:linear-gradient(135deg,#A96BC4,#E6A0D8); border:0; color:#17111A; font-weight:700; }
.stButton > button[kind="primary"]:hover { filter:brightness(1.08); }
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,[data-testid="stTextArea"] textarea { background:var(--card2); color:var(--text); border-color:var(--border); }
[data-testid="stDataFrame"],[data-testid="stDataEditor"] { border:1px solid var(--border); border-radius:12px; overflow:hidden; }
[data-testid="stExpander"] { border-color:var(--border); background:var(--card); border-radius:12px; }
div[data-testid="stAlert"] { border-radius:12px; }
@media (max-width:700px) { .block-container { padding-left:1rem;padding-right:1rem; }.hero {padding:2.25rem 1.2rem}.tier-card,.workflow-card {min-height:0} }
@media (prefers-reduced-motion:reduce) { *,*::before,*::after { transition:none!important;scroll-behavior:auto!important; } }
</style>
""", unsafe_allow_html=True)

PAGES = ["Home", "Application Requirements", "Infrastructure Data Source", "Infrastructure Assessment", "Placement Results", "Decision Explanation"]
STEPS = ["Define requirements", "Configure infrastructure", "Run assessment", "Review recommendation", "Understand decision"]
CAPABILITY_FIELDS = ("latency_ms", "data_stays_onsite", "compute", "bandwidth_mbps", "monthly_cost")
TIER_CARDS = [
    ("01", "◉", "On Device", "Process data directly on the user's device for immediate local response.", "LOCAL PROCESSING"),
    ("02", "⌁", "Far Edge", "Process data close to users with responsive local infrastructure.", "NEARBY COMPUTE"),
    ("03", "▦", "Regional Edge", "Use regional infrastructure for shared computing resources and services.", "REGIONAL SCALE"),
    ("04", "☁", "Cloud", "Use centralized infrastructure for scalable computing and storage.", "ELASTIC CAPACITY"),
]


def initialize_state():
    defaults = {"requirements": dict(DEFAULT_REQUIREMENTS), "profiles": get_demo_profiles(), "profiles_mode": "Demo profiles",
                "requirements_done": False, "profiles_done": False, "assessment": None, "assessment_outdated": False,
                "reviewed": False, "understood": False, "page_menu": "Home", "confirmed_profiles": None}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def go(page: str):
    st.session_state["_pending_page"] = page


def current_result():
    return st.session_state.assessment if st.session_state.assessment is not None and not st.session_state.assessment_outdated else None


def invalidate_assessment():
    if st.session_state.assessment is not None:
        st.session_state.assessment_outdated = True
        st.session_state.reviewed = False
        st.session_state.understood = False


def workflow():
    result = current_result()
    done = [st.session_state.requirements_done, st.session_state.profiles_done, result is not None,
            st.session_state.reviewed and result is not None, st.session_state.understood and result is not None]
    current_step = next((i for i, finished in enumerate(done) if not finished), 4)
    st.markdown("#### Your workflow")
    for i, (title, finished) in enumerate(zip(STEPS, done)):
        color = "#D77BCB" if i == current_step else ("#47C9A5" if finished else "#8E8493")
        mark = "✓" if finished else ("●" if i == current_step else "○")
        st.markdown(f'<div style="border-top:2px solid {color};padding:.55rem 0 .7rem;color:{color};font-size:.76rem;font-weight:700">{mark} &nbsp; {title}</div>', unsafe_allow_html=True)


def heading(kicker: str, title: str, subtitle: str = ""):
    st.markdown(f'<div class="eyebrow">{kicker}</div>', unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.markdown(f'<p class="muted">{subtitle}</p>', unsafe_allow_html=True)


def profile_errors(candidate):
    errors = []
    if not isinstance(candidate, Mapping):
        return ["Profiles must be a JSON object keyed by the four tier identifiers."]
    if set(candidate) != set(TIER_ORDER):
        errors.append("Include exactly these four tier keys: " + ", ".join(TIER_ORDER) + ".")
    for tier in TIER_ORDER:
        if tier not in candidate:
            continue
        profile = candidate[tier]
        if not isinstance(profile, Mapping):
            errors.append(f"{tier} must contain a capability object.")
            continue
        extra = set(profile) - set(CAPABILITY_FIELDS)
        if extra:
            errors.append(f"{tier} has unsupported fields: " + ", ".join(sorted(extra)))
        for field, value in profile.items():
            if field not in CAPABILITY_FIELDS or value is None:
                continue
            if field in {"latency_ms", "bandwidth_mbps", "monthly_cost"} and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
                errors.append(f"{tier}.{field} must be a finite nonnegative number or null.")
            elif field == "data_stays_onsite" and type(value) is not bool:
                errors.append(f"{tier}.{field} must be true, false, or null.")
            elif field == "compute" and value not in ("low", "medium", "high"):
                errors.append(f"{tier}.{field} must be low, medium, high, or null.")
    return errors


def profile_editor_frame(profiles):
    rows = []
    for tier in TIER_ORDER:
        profile = profiles.get(tier, {})
        rows.append({"Tier": TIER_LABELS[tier], **{field: profile.get(field) for field in CAPABILITY_FIELDS}})
    return pd.DataFrame(rows).set_index("Tier")


def edited_frame_to_profiles(frame):
    reverse = {label: key for key, label in TIER_LABELS.items()}
    profiles = {}
    for label, row in frame.iterrows():
        tier = reverse.get(label)
        if tier:
            profiles[tier] = {field: (None if pd.isna(row[field]) else row[field].item() if hasattr(row[field], "item") else row[field]) for field in CAPABILITY_FIELDS}
    return profiles


initialize_state()
if "_pending_page" in st.session_state:
    st.session_state.page_menu = st.session_state.pop("_pending_page")

with st.sidebar:
    st.markdown("<div class='eyebrow'>EDGEWISE</div>", unsafe_allow_html=True)
    st.markdown("### Placement Advisor")
    st.caption("Intelligent infrastructure placement")
    st.divider()
    st.selectbox("Navigate", PAGES, key="page_menu", label_visibility="collapsed")
    st.divider()
    workflow()
    st.divider()
    st.caption("Decision engine runs locally. Explanations never change its result.")

page = st.session_state.page_menu

if page == "Home":
    st.markdown('<section class="hero"><div class="eyebrow">EDGEWISE | INTELLIGENT PLACEMENT ADVISOR</div><h1>Where should your application run?</h1><p>Evaluate your application requirements against infrastructure capabilities to find feasible deployment options and understand the trade-offs.</p></section>', unsafe_allow_html=True)
    st.write("")
    cta, explore = st.columns([1, 1])
    with cta:
        if st.button("Define requirements  →", type="primary", use_container_width=True):
            go("Application Requirements"); st.rerun()
    with explore:
        st.markdown('<div style="text-align:center;padding:.65rem"><a href="#deployment-environments" style="color:#E6A0D8;text-decoration:none;font-weight:600">Explore environments ↓</a></div>', unsafe_allow_html=True)
    if st.session_state.assessment is not None:
        status = "Outdated · rerun assessment" if st.session_state.assessment_outdated else "Current assessment"
        st.info(status)
        if not st.session_state.assessment_outdated:
            recommendation = st.session_state.assessment["recommendation"]
            st.markdown(f"Latest recommendation: **{TIER_LABELS[recommendation]}**" if recommendation else "Latest assessment has no feasible recommendation.")
        if st.button("Open latest results"):
            go("Placement Results"); st.rerun()
    st.markdown('<div id="deployment-environments"></div>', unsafe_allow_html=True)
    st.subheader("Choose a deployment environment")
    st.markdown('<p class="muted">Four infrastructure tiers to evaluate against your application needs.</p>', unsafe_allow_html=True)
    cols = st.columns(4)
    for col, (number, icon, name, description, badge) in zip(cols, TIER_CARDS):
        with col:
            st.markdown(f'<div class="tier-card"><div class="card-number">{number}</div><div class="tier-icon">{icon}</div><h3>{name}</h3><p>{description}</p><span class="badge">{badge}</span></div>', unsafe_allow_html=True)
    st.write("")
    st.subheader("A clear path to a decision")
    st.markdown('<p class="muted">A transparent, feasibility-first assessment from inputs to recommendation.</p>', unsafe_allow_html=True)
    workflow_cards = [("01", "⌘", "Define your requirements", "Set the limits your application must meet."),
                      ("02", "⌕", "Evaluate infrastructure", "Compare infrastructure capabilities against mandatory constraints."),
                      ("03", "✧", "Discover your recommendation", "Review feasible options, trade-offs, and the final recommendation.")]
    cols = st.columns(3)
    for col, (number, icon, title, description) in zip(cols, workflow_cards):
        with col:
            st.markdown(f'<div class="workflow-card"><div class="card-number">{number} &nbsp; {icon}</div><h3>{title}</h3><p>{description}</p></div>', unsafe_allow_html=True)
    st.caption("Demonstration profiles are illustrative. EdgeWise does not discover live infrastructure.")

elif page == "Application Requirements":
    heading("Step 1 of 5", "Application requirements", "Set the workload limits that every placement option must satisfy.")
    req = st.session_state.requirements
    with st.form("requirements_form"):
        st.markdown("### Performance")
        latency = st.number_input("Maximum latency (ms)", min_value=0.0, value=float(req["max_latency_ms"]), step=1.0)
        st.markdown("### Compute and cost")
        compute, bandwidth, cost = st.columns(3)
        with compute:
            minimum_compute = st.selectbox("Minimum compute", ["low", "medium", "high"], index=["low", "medium", "high"].index(req["min_compute"]))
        with bandwidth:
            required_bandwidth = st.number_input("Required bandwidth (Mbps)", min_value=0.0, value=float(req["required_bandwidth_mbps"]), step=5.0)
        with cost:
            maximum_cost = st.number_input("Maximum monthly cost (INR)", min_value=0.0, value=float(req["max_monthly_cost"]), step=10.0)
        st.markdown("### Data residency")
        onsite = st.checkbox("Data must stay onsite", value=req["data_must_stay_onsite"])
        submitted = st.form_submit_button("Save requirements", type="primary", use_container_width=True)
    if submitted:
        updated = {"max_latency_ms": latency, "data_must_stay_onsite": onsite, "min_compute": minimum_compute,
                   "required_bandwidth_mbps": required_bandwidth, "max_monthly_cost": maximum_cost}
        if updated != st.session_state.requirements:
            invalidate_assessment()
        st.session_state.requirements = updated
        st.session_state.requirements_done = True
        st.success("Requirements saved.")
    back, forward = st.columns(2)
    with back:
        if st.button("← Back to Home", use_container_width=True): go("Home"); st.rerun()
    with forward:
        if st.button("Continue to infrastructure data →", type="primary", use_container_width=True): go("Infrastructure Data Source"); st.rerun()

elif page == "Infrastructure Data Source":
    heading("Step 2 of 5", "Infrastructure data source", "Preview the illustrative profiles or configure all four tiers with the approved capability fields.")
    mode = st.radio("Profile source", ["Demo profiles", "Custom configuration"], horizontal=True,
                    index=0 if st.session_state.profiles_mode == "Demo profiles" else 1, key="source_mode")
    if mode == "Demo profiles":
        st.info("These demonstration profiles are illustrative, not live telemetry, provider quotes, or automatic discovery.")
        st.dataframe(profile_editor_frame(get_demo_profiles()), use_container_width=True)
        confirmed = st.checkbox("I understand these profiles are illustrative", key="demo_confirm")
        if st.button("Use demo profiles", type="primary", disabled=not confirmed):
            demo = get_demo_profiles()
            if demo != st.session_state.profiles: invalidate_assessment()
            st.session_state.profiles = demo
            st.session_state.profiles_mode = mode
            st.session_state.profiles_done = True
            st.session_state.confirmed_profiles = json.dumps(demo, sort_keys=True)
            st.success("Demo profiles applied and confirmed.")
    else:
        st.caption("Canonical tiers: on_device, far_edge, regional_edge, cloud. Missing or null values remain unknown; unsupported fields are rejected.")
        editor = st.data_editor(profile_editor_frame(st.session_state.profiles), use_container_width=True, num_rows="fixed", key="profile_editor",
            column_config={"data_stays_onsite": st.column_config.CheckboxColumn("data_stays_onsite"),
                           "compute": st.column_config.SelectboxColumn("compute", options=["low", "medium", "high"]),
                           "latency_ms": st.column_config.NumberColumn("latency_ms", min_value=0, format="%.2f"),
                           "bandwidth_mbps": st.column_config.NumberColumn("bandwidth_mbps", min_value=0, format="%.2f"),
                           "monthly_cost": st.column_config.NumberColumn("monthly_cost (INR)", min_value=0, format="%.2f")})
        st.caption("For nullable boolean capabilities or explicit null values, use the JSON editor below.")
        uploaded = st.file_uploader("Upload tier-keyed JSON", type=["json"], key="profile_json_upload")
        initial_json = json.dumps(st.session_state.profiles, indent=2, allow_nan=False)
        if "profile_json_text" not in st.session_state:
            st.session_state["profile_json_text"] = initial_json
        json_text = st.text_area("Tier-keyed JSON editor", height=260, key="profile_json_text")
        if uploaded is not None and st.button("Load uploaded JSON", key="load_upload"):
            try:
                st.session_state["profile_json_text"] = uploaded.getvalue().decode("utf-8")
                st.rerun()
            except (UnicodeDecodeError, ValueError) as exc:
                st.error(f"Could not read the uploaded JSON file: {exc}")
        import_mode = st.radio("Configuration to validate", ["Editable table", "JSON editor / upload"], horizontal=True)
        candidate = None
        parse_error = None
        try:
            candidate = edited_frame_to_profiles(editor) if import_mode == "Editable table" else json.loads(json_text)
            errors = profile_errors(candidate)
            if errors:
                st.error("Configuration needs attention: " + " ".join(errors))
            else:
                st.success("All four tiers and approved capability fields validate. Unknown values are preserved.")
                st.dataframe(profile_editor_frame(candidate), use_container_width=True)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            parse_error = exc
            st.error(f"Could not parse profile data: {exc}")
        valid = candidate is not None and not profile_errors(candidate) and parse_error is None
        confirmed = st.checkbox("Confirm this custom configuration", key="custom_confirm", disabled=not valid)
        if st.button("Validate and apply custom profiles", type="primary", disabled=not (valid and confirmed)):
            if candidate != st.session_state.profiles: invalidate_assessment()
            st.session_state.profiles = candidate
            st.session_state.profiles_mode = mode
            st.session_state.profiles_done = True
            st.session_state.confirmed_profiles = json.dumps(candidate, sort_keys=True)
            st.success("Custom profiles validated, previewed, and applied.")
    back, forward = st.columns(2)
    with back:
        if st.button("← Back to requirements", use_container_width=True): go("Application Requirements"); st.rerun()
    with forward:
        if st.button("Continue to assessment →", type="primary", disabled=not st.session_state.profiles_done, use_container_width=True): go("Infrastructure Assessment"); st.rerun()

elif page == "Infrastructure Assessment":
    heading("Step 3 of 5", "Infrastructure assessment", "The local decision engine validates inputs, checks hard constraints, scores feasible tiers only, then ranks feasible candidates.")
    st.markdown("#### Saved requirements")
    st.json(st.session_state.requirements)
    st.markdown(f"#### Active infrastructure data source · {st.session_state.profiles_mode}")
    st.dataframe(profile_editor_frame(st.session_state.profiles), use_container_width=True)
    if not st.session_state.requirements_done or not st.session_state.profiles_done:
        st.warning("Save requirements and confirm an infrastructure data source before running an assessment.")
    if st.session_state.assessment_outdated:
        st.warning("Inputs changed after the last run. Rerun the assessment before viewing current results.")
    if st.button("Run Placement Assessment", type="primary", disabled=not (st.session_state.requirements_done and st.session_state.profiles_done), use_container_width=True):
        st.session_state.assessment = evaluate_placement(st.session_state.requirements, st.session_state.profiles)
        st.session_state.assessment_outdated = False
        st.session_state.reviewed = False
        st.session_state.understood = False
        st.success("Assessment calculated from the current requirements and profiles.")
    result = current_result()
    if result is not None:
        if result["valid"]:
            for tier in result["tiers"]:
                with st.expander(f"{TIER_LABELS[tier['tier']]} · {tier['status']}"):
                    for reason in tier["reasons"]: st.write(f"- {reason}")
        else:
            st.error("The engine rejected the assessment inputs.")
            for error in result["errors"]: st.write(f"- {error}")
        if st.button("View Placement Results →", type="primary", disabled=not result["valid"]): go("Placement Results"); st.rerun()
    if st.button("← Back to infrastructure data"): go("Infrastructure Data Source"); st.rerun()

elif page == "Placement Results":
    heading("Step 4 of 5", "Placement results", "Feasibility comes first. Only tiers that pass every known hard constraint are scored and ranked.")
    result = current_result()
    if result is None:
        st.warning("There is no current result. Run or rerun the assessment to see results.")
        if st.button("Go to assessment", type="primary"): go("Infrastructure Assessment"); st.rerun()
    elif not result["valid"]:
        st.error("The assessment inputs were rejected.")
        for error in result["errors"]: st.write(f"- {error}")
    else:
        counts = {status: sum(tier["status"] == status for tier in result["tiers"]) for status in ("FEASIBLE", "INFEASIBLE", "UNVERIFIED")}
        a, b, c = st.columns(3)
        a.metric("FEASIBLE", counts["FEASIBLE"]); b.metric("INFEASIBLE", counts["INFEASIBLE"]); c.metric("UNVERIFIED", counts["UNVERIFIED"])
        if result["recommendation"]:
            selected = next(tier for tier in result["tiers"] if tier["tier"] == result["recommendation"])
            st.markdown(f'<div class="soft-card"><div class="eyebrow">Recommended placement</div><h2>{TIER_LABELS[result["recommendation"]]}</h2><p>Actual suitability score: <b>{selected["score"]:.2f}/100</b> · relative suitability, not a probability.</p></div>', unsafe_allow_html=True)
        else:
            st.warning("No recommendation: no tier has confirmed feasibility.")
            if counts["UNVERIFIED"]:
                st.write("Required capability data remains unknown for one or more tiers. See constraint evidence below.")
            elif counts["INFEASIBLE"]:
                st.write("Known hard constraints failed for all tiers. See each engine-provided constraint reason below.")
        st.subheader("Feasible-only ranking")
        st.dataframe(pd.DataFrame([{"Rank": row["rank"], "Tier": TIER_LABELS[row["tier"]], "Score": row["score"]} for row in result["ranking"]]), hide_index=True, use_container_width=True)
        st.subheader("All tier capabilities")
        rows = []
        for tier in result["tiers"]:
            profile = st.session_state.profiles[tier["tier"]]
            show = lambda value: "Unknown" if value is None else value
            rows.append({"Tier": TIER_LABELS[tier["tier"]], "Status": tier["status"], "Latency (ms)": show(profile.get("latency_ms")),
                         "Data onsite": show(profile.get("data_stays_onsite")), "Compute": show(profile.get("compute")),
                         "Bandwidth (Mbps)": show(profile.get("bandwidth_mbps")), "Monthly cost (INR)": show(profile.get("monthly_cost")),
                         "Score": tier["score"] if tier["score"] is not None else "—",
                         "Rank": next((row["rank"] for row in result["ranking"] if row["tier"] == tier["tier"]), "—")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.subheader("Constraint evidence")
        for tier in result["tiers"]:
            with st.expander(f"{TIER_LABELS[tier['tier']]} · {tier['status']}", expanded=tier["tier"] == result["recommendation"]):
                st.markdown(f"**Engine status: {tier['status']}**")
                for con in tier["constraints"]:
                    st.markdown(f"**{con['constraint']} · {con['status']}**  \n{con['reason']}  \nActual: `{con['actual'] if con['actual'] is not None else 'Unknown'}` · Required: `{con['required'] if con['required'] is not None else 'Not applicable'}`")
                if tier["score_breakdown"]:
                    st.markdown("**Actual score breakdown and weights**")
                    breakdown = tier["score_breakdown"]
                    st.dataframe(pd.DataFrame([{"Factor": name.replace("_", " ").title(), "Weight": factor["weight"], "Normalized utility": factor["normalized_value"], "Weighted points": factor["weighted_points"]} for name, factor in breakdown.items() if name != "total_score"]), hide_index=True, use_container_width=True)
                st.markdown("**Engine reasons**")
                for reason in tier["reasons"]: st.write(f"- {reason}")
        st.caption("Suitability scores compare relative trade-offs; they are not probabilities. Demonstration data is illustrative.")
        report = {"requirements": st.session_state.requirements, "profiles": st.session_state.profiles, "assessment": result}
        st.download_button("Download JSON report", json.dumps(report, indent=2, allow_nan=False), file_name="edgewise-assessment.json", mime="application/json", type="primary")
        st.checkbox("I reviewed the feasibility and ranking", key="reviewed")
        if st.session_state.reviewed and st.button("Continue to Decision Explanation →", type="primary"): go("Decision Explanation"); st.rerun()
        if st.button("← Back to assessment"): go("Infrastructure Assessment"); st.rerun()

elif page == "Decision Explanation":
    heading("Step 5 of 5", "Decision explanation", "The structured engine result remains authoritative; explanation text cannot change scores, statuses, constraints, ranking, or recommendation.")
    result = current_result()
    if result is None:
        st.info("Run a current assessment to see its explanation.")
        if st.button("Go to assessment", type="primary"): go("Infrastructure Assessment"); st.rerun()
    elif not result["valid"]:
        st.error("The engine did not produce a valid assessment.")
        for error in result["errors"]: st.write(f"- {error}")
    else:
        explanation = explain_assessment(result)
        st.markdown('<div class="soft-card"><div class="eyebrow">Local explanation</div><h3>Executive summary</h3><p>'+explanation+'</p></div>', unsafe_allow_html=True)
        if result["recommendation"]:
            selected = next(tier for tier in result["tiers"] if tier["tier"] == result["recommendation"])
            st.subheader("Why this recommendation was selected")
            st.write(f"{TIER_LABELS[result['recommendation']]} is the engine's highest-ranked feasible tier. Its actual relative suitability score is {selected['score']:.2f}/100.")
        else:
            st.subheader("Why there is no recommendation")
            st.write("The decision engine found no tier with confirmed feasibility. See each tier's actual status and constraint evidence in Placement Results.")
        st.subheader("Constraint evaluation and score details")
        for tier in result["tiers"]:
            with st.expander(f"{TIER_LABELS[tier['tier']]} · {tier['status']}"):
                for con in tier["constraints"]: st.write(f"**{con['constraint']} · {con['status']}** — {con['reason']} (actual: {con['actual']}, required: {con['required']})")
                if tier["score_breakdown"]:
                    breakdown = tier["score_breakdown"]
                    st.dataframe(pd.DataFrame([{"Factor": name.replace("_", " ").title(), "Weight": factor["weight"], "Normalized utility": factor["normalized_value"], "Weighted points": factor["weighted_points"]} for name, factor in breakdown.items() if name != "total_score"]), hide_index=True, use_container_width=True)
        st.subheader("Feasible alternatives")
        alternatives = [row for row in result["ranking"] if row["tier"] != result["recommendation"]]
        if alternatives:
            st.dataframe(pd.DataFrame([{"Rank": row["rank"], "Tier": TIER_LABELS[row["tier"]], "Score": row["score"]} for row in alternatives]), hide_index=True, use_container_width=True)
        else:
            st.caption("No additional feasible alternatives are available.")
        st.checkbox("I understand this decision and its trade-offs", key="understood")
        if st.session_state.understood: st.success("Workflow complete. The structured result remains the source of truth.")
        back, results = st.columns(2)
        with back:
            if st.button("← Back to assessment", use_container_width=True): go("Infrastructure Assessment"); st.rerun()
        with results:
            if st.button("Back to Placement Results", use_container_width=True): go("Placement Results"); st.rerun()
