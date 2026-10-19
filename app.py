"""EdgeWise — Intelligent Infrastructure Placement Advisor."""

from __future__ import annotations

import json
from copy import deepcopy
from collections.abc import Mapping
from datetime import datetime, timezone
from html import escape
import logging
from uuid import uuid4

import pandas as pd
import streamlit as st

from ai_explainer import DecisionExplanation, explain_assessment, explain_decision
from decision_engine import TIER_ORDER, evaluate_placement
from infrastructure_data import (
    DEFAULT_REQUIREMENTS,
    TIER_LABELS,
    get_demo_profiles,
    validate_profiles,
    validate_requirements,
)

st.set_page_config(page_title="EdgeWise | Placement Advisor", page_icon="◉", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root { color-scheme:light; --bg:#F7F6F3; --side:#F1EFEA; --card:#FFFFFF; --card2:#F5F3EF; --pink:#A64C69; --purple:#8B4F76; --terracotta:#A9462D; --text:#282522; --muted:#625D57; --border:#DDD8D0; --success:#2E6947; --warning:#765719; --error:#963C32; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; color:var(--text); }
h1,h2,h3 { font-family:'Manrope',sans-serif; letter-spacing:-.035em; color:var(--text); }
.stApp { background:var(--bg); color:var(--text); }
.block-container { max-width:1320px; padding-top:2rem; padding-bottom:4rem; }
.eyebrow { color:var(--terracotta); font-size:.73rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase; margin-bottom:.65rem; }
.hero { position:relative; isolation:isolate; overflow:hidden; text-align:center; background:linear-gradient(145deg,#FFFDFC,#F1EAE4); border:1px solid var(--border); border-radius:22px; padding:3.4rem 2rem 3rem; }
.hero:before { content:''; position:absolute; z-index:-1; width:420px;height:240px;top:-100px;left:calc(50% - 210px);background:rgba(169,70,45,.10);filter:blur(75px);border-radius:50%; }
.hero h1 { font-size:clamp(2.4rem,5.4vw,4.5rem); line-height:1.08; margin:.35rem 0 1rem; color:var(--text); }
.hero p { color:var(--muted); font-size:1.08rem; max-width:780px; margin:.7rem auto 0; line-height:1.7; }
.soft-card,.tier-card,.workflow-card { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:1.25rem 1.35rem; height:100%; transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease; color:var(--text); }
.tier-card { min-height:224px; background:linear-gradient(155deg,#FFFFFF,#F7F3EF); border-color:#DCCFC8; }
.tier-card:hover,.workflow-card:hover { transform:translateY(-2px); border-color:var(--terracotta); box-shadow:0 8px 22px rgba(75,48,34,.08); }
.card-number,.tier-name { color:var(--muted); font-size:.77rem; letter-spacing:.08em; }
.tier-icon { color:var(--terracotta); font-size:1.45rem; margin:.45rem 0; }
.tier-card h3 { margin:.15rem 0 .45rem; font-size:1.23rem; }
.tier-card p,.workflow-card p { color:var(--muted); line-height:1.55; font-size:.92rem; }
.badge { display:inline-block; margin-top:.4rem; color:var(--purple); font-size:.68rem; letter-spacing:.11em; font-weight:700; }
.workflow-card { min-height:178px; }
.workflow-card h3 { font-size:1.08rem; margin:.55rem 0 .3rem; }
.metric-value { font-family:'Manrope',sans-serif; font-size:1.45rem; font-weight:700; margin-top:.25rem; }
.muted, [data-testid="stCaptionContainer"] { color:var(--muted)!important; }
[data-testid="stSidebar"] { background:var(--side); border-right:1px solid var(--border); }
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { color:var(--text); }
.stButton > button, .stDownloadButton > button { border-radius:10px; border:1px solid var(--border); color:var(--text); background:#FFFFFF; transition:transform .18s ease,border-color .18s ease; }
.stButton > button:hover,.stDownloadButton > button:hover { border-color:var(--terracotta); transform:translateY(-1px); color:var(--text); }
.stButton > button[kind="primary"],.stDownloadButton > button[kind="primary"] { background:var(--terracotta); border:1px solid var(--terracotta); color:#FFFFFF; font-weight:700; }
.stButton > button[kind="primary"]:hover { background:#873722; border-color:#873722; }
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,[data-testid="stTextArea"] textarea { background:#FFFFFF; color:var(--text); border-color:var(--border); }
[data-testid="stDataFrame"],[data-testid="stDataEditor"] { border:1px solid var(--border); border-radius:12px; overflow:hidden; }
[data-testid="stExpander"] { border-color:var(--border); background:var(--card); border-radius:12px; }
[data-testid="stMetricLabel"] { color:var(--muted); }
div[data-testid="stAlert"] { border-radius:12px; }
@media (max-width:700px) { .block-container { padding-left:1rem;padding-right:1rem; }.hero {padding:2.25rem 1.2rem}.tier-card,.workflow-card {min-height:0} }
@media (prefers-reduced-motion:reduce) { *,*::before,*::after { transition:none!important;scroll-behavior:auto!important; } }
</style>
""", unsafe_allow_html=True)

PAGES = ["Home", "Dashboard", "Application Requirements", "Infrastructure Data Source",
         "Infrastructure Assessment", "Placement Results", "Decision Explanation"]
STEPS = ["Define Requirements", "Configure Infrastructure", "Run Assessment", "Review Recommendation", "Understand the Decision"]
STEP_SHORT_LABELS = ["Requirements", "Infrastructure", "Assessment", "Results", "Explanation"]
PAGE_STEP_INDEX = {
    "Application Requirements": 0,
    "Infrastructure Data Source": 1,
    "Infrastructure Assessment": 2,
    "Placement Results": 3,
    "Decision Explanation": 4,
}
CAPABILITY_FIELDS = ("latency_ms", "data_stays_onsite", "compute", "bandwidth_mbps", "monthly_cost")
LOGGER = logging.getLogger("edgewise")


def initialize_state():
    defaults = {
        "requirements": dict(DEFAULT_REQUIREMENTS), "profiles": get_demo_profiles(),
        "profiles_mode": "Demo profiles", "requirements_done": False, "profiles_done": False,
        "assessment": None, "assessment_outdated": False, "reviewed": False, "understood": False,
        "assessment_requirements_snapshot": None, "assessment_profiles_snapshot": None,
        "assessment_id": None, "assessment_created_at": None,
        "explanation_generated_for_assessment_id": None,
        "decision_explanation": None,
        "custom_profiles_draft": get_demo_profiles(), "pending_profiles_json": None,
        "profile_json_sync": False,
        "profile_mode_migrated": False,
        "page_menu": "Home", "pending_page": None, "profile_source_mode": "Demo profiles",
        "workflow_notice": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = deepcopy(value)
    for field, value in st.session_state.requirements.items():
        key = f"draft_{field}"
        if key not in st.session_state:
            st.session_state[key] = value
    if "profiles_json_draft" not in st.session_state:
        st.session_state.profiles_json_draft = json.dumps(st.session_state.profiles, indent=2, allow_nan=False)
    if not st.session_state.profile_mode_migrated:
        saved_mode = st.session_state.profiles_mode
        normalized_mode = "Custom data" if saved_mode in ("Custom data", "Custom configuration") else "Demo profiles"
        st.session_state.profile_source_mode = normalized_mode
        st.session_state.profiles_mode = normalized_mode
        st.session_state.profile_mode_migrated = True


def go(page: str):
    # Widget-backed state cannot be changed after its widget is instantiated.
    # Apply the route at the beginning of the next run instead.
    st.session_state.pending_page = page


def status_chip(status: str):
    palette = {"FEASIBLE": ("#EAF3EA", "#315C38"), "INFEASIBLE": ("#F8EAE5", "#9C4128"), "UNVERIFIED": ("#F5F0E3", "#78601C")}
    bg, fg = palette.get(status, ("#F8F8F7", "#686868"))
    st.markdown(f'<span style="display:inline-block;padding:.3rem .65rem;border-radius:999px;background:{bg};color:{fg};font-size:.76rem;font-weight:700;letter-spacing:.04em">{status}</span>', unsafe_allow_html=True)


def current_result():
    assessment = st.session_state.assessment
    if (not isinstance(assessment, Mapping) or not assessment.get("valid")
            or not st.session_state.assessment_id or st.session_state.assessment_outdated):
        return None
    if st.session_state.assessment_requirements_snapshot != st.session_state.requirements:
        return None
    if st.session_state.assessment_profiles_snapshot != st.session_state.profiles:
        return None
    return assessment


def has_outdated_result():
    return st.session_state.assessment is not None and (
        st.session_state.assessment_outdated
        or not st.session_state.assessment_id
        or st.session_state.assessment_requirements_snapshot != st.session_state.requirements
        or st.session_state.assessment_profiles_snapshot != st.session_state.profiles
    )


def workflow_completion():
    result = current_result()
    return [
        st.session_state.requirements_done,
        st.session_state.profiles_done,
        result is not None,
        st.session_state.reviewed and result is not None,
        st.session_state.explanation_generated_for_assessment_id == st.session_state.assessment_id
        and result is not None,
    ]


def workflow_states():
    done = workflow_completion()
    viewing_step = PAGE_STEP_INDEX.get(st.session_state.page_menu)
    current_step = viewing_step if viewing_step is not None else next((i for i, finished in enumerate(done) if not finished), 4)
    states = []
    for index, finished in enumerate(done):
        if finished:
            state = "Completed" if viewing_step != index else "Completed · viewing"
        elif index >= 2 and has_outdated_result():
            state = "Outdated"
        elif index == current_step:
            state = "Current"
        else:
            state = "Upcoming"
        states.append(state)
    return done, states, viewing_step


def workflow_destination(step_index: int) -> tuple[str, str]:
    """Route a workflow-step click without marking incomplete work complete."""
    if step_index == 0:
        return "Application Requirements", ""
    if step_index == 1:
        if not st.session_state.requirements_done:
            return "Application Requirements", "Save your requirements before configuring infrastructure."
        return "Infrastructure Data Source", ""
    if step_index == 2:
        if not st.session_state.requirements_done:
            return "Application Requirements", "Save your requirements before running an assessment."
        if not st.session_state.profiles_done:
            return "Infrastructure Data Source", "Apply infrastructure profiles before running an assessment."
        return "Infrastructure Assessment", ""
    if step_index == 3:
        if current_result() is not None:
            return "Placement Results", ""
        return workflow_destination(2)
    # The explanation is based on the current assessment; never mark the
    # recommendation review complete merely because the user opened it.
    if current_result() is None:
        target, message = workflow_destination(2)
        return target, message or "Run a current assessment before understanding its decision."
    return "Decision Explanation", ""


def workflow():
    done, states, viewing_step = workflow_states()
    st.markdown("#### Assessment workflow")
    for i, title in enumerate(STEPS):
        state = states[i]
        mark = "✓" if done[i] else "!" if state == "Outdated" else "●" if state == "Current" else "○"
        if st.button(f"{mark}   {i + 1}. {STEP_SHORT_LABELS[i]}", key=f"workflow_step_{i}",
                     type="primary" if viewing_step == i else "secondary", use_container_width=True,
                     help=f"Open {title}. Incomplete steps are routed to the next required action."):
            target, notice = workflow_destination(i)
            if i == 4 and target == "Decision Explanation":
                st.session_state.reviewed = True
            st.session_state.workflow_notice = notice
            go(target)
            st.rerun()
        st.caption(state)


def heading(kicker: str, title: str, subtitle: str = ""):
    st.markdown(f'<div class="eyebrow">{kicker}</div>', unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.markdown(f'<p class="muted">{subtitle}</p>', unsafe_allow_html=True)


def profile_errors(candidate):
    return validate_profiles(candidate)


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
if st.session_state.pending_page:
    st.session_state.page_menu = st.session_state.pending_page
    st.session_state.pending_page = None

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
st.markdown('<div class="eyebrow">EDGEWISE / INTELLIGENT INFRASTRUCTURE PLACEMENT</div>', unsafe_allow_html=True)
if st.session_state.workflow_notice:
    st.info(st.session_state.workflow_notice)
    st.session_state.workflow_notice = ""

if page == "Home":
    st.markdown('<section class="hero"><div class="eyebrow">EDGEWISE · INTELLIGENT PLACEMENT ADVISOR</div><h1>Where should your application run?</h1><p>Compare your workload requirements with infrastructure capabilities. See which tiers meet every hard constraint, then understand the trade-offs behind the ranking.</p></section>', unsafe_allow_html=True)
    st.write("")
    left, right = st.columns([1, 1])
    with left:
        if st.button("Start assessment", type="primary", use_container_width=True):
            go("Application Requirements")
            st.rerun()
    with right:
        if has_outdated_result():
            st.markdown("<div class='muted' style='padding:.65rem 0'>The previous assessment is outdated because inputs changed. Run it again to see current results.</div>", unsafe_allow_html=True)
        elif current_result() is None:
            st.markdown("<div class='muted' style='padding:.65rem 0'>No assessment has been run in this session yet.</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='muted' style='padding:.65rem 0'>A current assessment is available in your results.</div>", unsafe_allow_html=True)
            if st.button("Open latest results", use_container_width=True):
                go("Placement Results"); st.rerun()
    st.subheader("Choose a deployment environment")
    st.markdown('<p class="muted">EdgeWise evaluates the same five capabilities for each of these four tiers.</p>', unsafe_allow_html=True)
    cols = st.columns(4)
    cards = [
        ("01", "◉", "On Device", "Process data directly on the workload device.", "LOCAL PROCESSING"),
        ("02", "⌁", "Far Edge", "Run compute close to users and connected devices.", "NEARBY COMPUTE"),
        ("03", "▦", "Regional Edge", "Share infrastructure across a regional footprint.", "REGIONAL SCALE"),
        ("04", "☁", "Cloud", "Use centralized infrastructure for elastic capacity.", "ELASTIC CAPACITY"),
    ]
    for col, (number, icon, name, description, badge) in zip(cols, cards):
        col.markdown(f"<div class='tier-card'><div class='card-number'>{number}</div><div class='tier-icon'>{icon}</div><h3>{name}</h3><p>{description}</p><span class='badge'>{badge}</span></div>", unsafe_allow_html=True)
    st.subheader("A clear path to a decision")
    flow_cards = [
        ("01", "Define", "Save workload requirements and the limits every placement must meet."),
        ("02", "Compare", "Check the actual tier profiles against hard constraints."),
        ("03", "Understand", "Review feasible options, score trade-offs, and unknowns."),
    ]
    cols = st.columns(3)
    for col, (number, title, description) in zip(cols, flow_cards):
        col.markdown(f"<div class='workflow-card'><div class='card-number'>{number}</div><h3>{title}</h3><p>{description}</p></div>", unsafe_allow_html=True)
    st.caption("Demonstration profiles are illustrative, not live measurements or provider quotes.")

elif page == "Dashboard":
    heading("Workspace", "Assessment dashboard", "A live view of progress in this session.")
    done, states, _ = workflow_states()
    st.subheader("Assessment workflow")
    for number, (step, state) in enumerate(zip(STEPS, states), start=1):
        left, right = st.columns([4, 1])
        left.markdown(f"**{number}. {step}**")
        right.markdown(f"`{state}`")
    result = current_result()
    if result is None:
        if has_outdated_result():
            st.warning("Your previous assessment is outdated because requirements or infrastructure profiles changed. Reassess to produce current results.")
        else:
            st.info("Your latest assessment will appear here after you run one.")
        if st.button("Define requirements", type="primary"):
            go("Application Requirements"); st.rerun()
    else:
        st.subheader("Latest assessment")
        if result["recommendation"]:
            st.success(f"Recommended placement: {TIER_LABELS[result['recommendation']]}")
        else:
            st.warning("No confirmed feasible placement is available.")
        st.dataframe(pd.DataFrame([{"Tier": TIER_LABELS[t["tier"]], "Status": t["status"], "Suitability score": t["score"]} for t in result["tiers"]]), hide_index=True, use_container_width=True)
        view, new = st.columns(2)
        if view.button("View Placement Results", type="primary"):
            go("Placement Results"); st.rerun()
        if new.button("Start New Assessment"):
            st.session_state.assessment = None
            st.session_state.assessment_id = None
            st.session_state.assessment_created_at = None
            st.session_state.assessment_requirements_snapshot = None
            st.session_state.assessment_profiles_snapshot = None
            st.session_state.assessment_outdated = False
            st.session_state.reviewed = st.session_state.understood = False
            st.session_state.explanation_generated_for_assessment_id = None
            go("Application Requirements"); st.rerun()

elif page == "Application Requirements":
    heading("Step 1 of 5", "Application requirements", "Set the workload limits that every placement option must satisfy.")
    req = st.session_state.requirements
    with st.form("requirements_form"):
        c1, c2 = st.columns(2)
        with c1:
            latency = st.number_input("Maximum latency (ms)", min_value=0.0, value=float(st.session_state.draft_max_latency_ms), step=1.0, key="draft_max_latency_ms")
            onsite = st.checkbox("Data must stay onsite", value=st.session_state.draft_data_must_stay_onsite, key="draft_data_must_stay_onsite")
            compute = st.selectbox("Minimum compute", ["low", "medium", "high"], index=["low", "medium", "high"].index(st.session_state.draft_min_compute), key="draft_min_compute")
        with c2:
            bandwidth = st.number_input("Required bandwidth (Mbps)", min_value=0.0, value=float(st.session_state.draft_required_bandwidth_mbps), step=5.0, key="draft_required_bandwidth_mbps")
            cost = st.number_input("Maximum monthly cost", min_value=0.0, value=float(st.session_state.draft_max_monthly_cost), step=10.0, key="draft_max_monthly_cost")
        submitted = st.form_submit_button("Save Requirements & Continue", type="primary", use_container_width=True)
    if submitted:
        updated = {"max_latency_ms": latency, "data_must_stay_onsite": onsite, "min_compute": compute,
                   "required_bandwidth_mbps": bandwidth, "max_monthly_cost": cost}
        errors = validate_requirements(updated)
        if errors:
            for error in errors: st.error(error)
        else:
            changed = updated != st.session_state.requirements
            st.session_state.requirements = updated
            st.session_state.requirements_done = True
            if changed and st.session_state.assessment is not None:
                st.session_state.assessment_outdated = True
                st.session_state.reviewed = st.session_state.understood = False
                st.session_state.explanation_generated_for_assessment_id = None
            go("Infrastructure Data Source"); st.rerun()
    st.caption("The form contains exactly the five supported requirement fields.")
    if st.button("Back to Dashboard"):
        go("Dashboard"); st.rerun()

elif page == "Infrastructure Data Source":
    heading("Step 2 of 5", "Infrastructure data source", "Use the illustrative profiles or provide capability data in the exact tier-keyed schema.")
    mode = st.radio("Profile source", ["Demo profiles", "Custom data"], horizontal=True,
                    key="profile_source_mode")
    if mode == "Demo profiles":
        st.info("These demonstration profiles are illustrative, not live telemetry, provider quotes, or automatic discovery.")
        st.dataframe(profile_editor_frame(get_demo_profiles()), use_container_width=True)
        save_demo = st.button("Save Infrastructure & Continue", type="primary")
        if save_demo:
            changed = st.session_state.profiles != get_demo_profiles()
            st.session_state.profiles = get_demo_profiles()
            st.session_state.profiles_mode = mode
            st.session_state.profiles_done = True
            if changed and st.session_state.assessment is not None:
                st.session_state.assessment_outdated = True
                st.session_state.reviewed = st.session_state.understood = False
                st.session_state.explanation_generated_for_assessment_id = None
            go("Infrastructure Assessment"); st.rerun()
    else:
        st.caption("Set unknown capabilities to null or leave them blank. Extra fields are rejected.")
        editor = st.data_editor(profile_editor_frame(st.session_state.profiles), use_container_width=True,
                                num_rows="fixed", key="profile_editor",
                                column_config={"data_stays_onsite": st.column_config.SelectboxColumn("data_stays_onsite", options=[True, False, None]),
                                               "compute": st.column_config.SelectboxColumn("compute", options=["low", "medium", "high", None]),
                                               "latency_ms": st.column_config.NumberColumn("latency_ms", min_value=0),
                                               "bandwidth_mbps": st.column_config.NumberColumn("bandwidth_mbps", min_value=0),
                                               "monthly_cost": st.column_config.NumberColumn("monthly_cost", min_value=0)})
        uploaded = st.file_uploader("Import JSON file", type=["json"])
        if st.session_state.pending_profiles_json is not None:
            st.session_state.profiles_json_draft = st.session_state.pending_profiles_json
            st.session_state.pending_profiles_json = None
        json_text = st.text_area("Or paste profiles as JSON", key="profiles_json_draft", height=230)
        import_mode = st.radio("Apply from", ["Table editor", "JSON input"], horizontal=True)
        if uploaded is not None and st.button("Load uploaded JSON", key="load_upload"):
            try:
                st.session_state.pending_profiles_json = uploaded.getvalue().decode("utf-8")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not read the uploaded JSON file: {exc}")
        save_custom = st.button("Save Infrastructure & Continue", type="primary")
        if save_custom:
            try:
                candidate = edited_frame_to_profiles(editor) if import_mode == "Table editor" else json.loads(json_text)
                errors = profile_errors(candidate)
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    changed = candidate != st.session_state.profiles
                    st.session_state.profiles = candidate
                    st.session_state.profiles_mode = mode
                    st.session_state.profiles_done = True
                    if changed and st.session_state.assessment is not None:
                        st.session_state.assessment_outdated = True
                        st.session_state.reviewed = st.session_state.understood = False
                        st.session_state.explanation_generated_for_assessment_id = None
                    st.session_state.custom_profiles_draft = deepcopy(candidate)
                    go("Infrastructure Assessment"); st.rerun()
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                st.error(f"Could not parse profile data: {exc}")
    applied_source_matches = mode == st.session_state.profiles_mode
    if not applied_source_matches:
        st.info(f"{mode} is selected but not applied yet. Apply it before continuing.")
    if st.button("Back to Requirements"):
        go("Application Requirements"); st.rerun()

elif page == "Infrastructure Assessment":
    heading("Step 3 of 5", "Run infrastructure assessment", "Hard constraints are checked before suitability scores are calculated.")
    if not st.session_state.requirements_done:
        st.warning("Save application requirements before running an assessment.")
        if st.button("Define requirements", type="primary"):
            go("Application Requirements"); st.rerun()
    elif not st.session_state.profiles_done:
        st.warning("Apply an infrastructure data source before running an assessment.")
        if st.button("Configure infrastructure", type="primary"):
            go("Infrastructure Data Source"); st.rerun()
    else:
        st.markdown("<div class='soft-card'><b>Assessment inputs</b><br><span class='muted'>Requirements and infrastructure profiles currently saved in this session.</span></div>", unsafe_allow_html=True)
        st.write("")
        if st.button("Run Assessment", type="primary", use_container_width=True):
            errors = validate_requirements(st.session_state.requirements) + validate_profiles(st.session_state.profiles)
            if errors:
                for error in errors: st.error(error)
            else:
                try:
                    assessment = evaluate_placement(st.session_state.requirements, st.session_state.profiles)
                    if not assessment.get("valid"):
                        for error in assessment.get("errors", []): st.error(error)
                    else:
                        st.session_state.assessment = assessment
                        st.session_state.assessment_requirements_snapshot = deepcopy(st.session_state.requirements)
                        st.session_state.assessment_profiles_snapshot = deepcopy(st.session_state.profiles)
                        st.session_state.assessment_id = uuid4().hex
                        st.session_state.assessment_created_at = datetime.now(timezone.utc).isoformat()
                        st.session_state.assessment_outdated = False
                        st.session_state.reviewed = st.session_state.understood = False
                        st.session_state.explanation_generated_for_assessment_id = None
                        go("Placement Results"); st.rerun()
                except Exception as exc:
                    LOGGER.exception("Placement assessment failed")
                    st.error(f"Assessment could not be completed: {exc}")
        if st.button("Back to Infrastructure"):
            go("Infrastructure Data Source"); st.rerun()
        if current_result() is not None and st.button("Review placement results"):
            go("Placement Results"); st.rerun()
        result = current_result()
        if result is not None:
            st.subheader("Tier assessment details")
            for tier in result["tiers"]:
                with st.expander(f"{TIER_LABELS[tier['tier']]} · {tier['status']}", expanded=True):
                    status_chip(tier["status"])
                    for reason in tier["reasons"]:
                        st.write(reason)
                    st.dataframe(pd.DataFrame([{"Constraint": item["constraint"], "Status": item["status"],
                        "Actual": repr(item["actual"]), "Required": repr(item["required"]), "Reason": item["reason"]}
                        for item in tier["constraints"]]), hide_index=True, use_container_width=True)

elif page == "Placement Results":
    heading("Step 4 of 5", "Placement results", "Feasibility comes first. Only tiers that pass every known hard constraint are scored and ranked.")
    result = current_result()
    if result is None:
        if has_outdated_result():
            st.warning("This assessment is outdated because its inputs changed. Run a new assessment before using a recommendation.")
        else:
            st.info("There is no current assessment yet. Run the engine after saving your requirements and infrastructure data.")
        if st.button("Go to assessment", type="primary"):
            go("Infrastructure Assessment"); st.rerun()
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
        st.caption("Suitability scores compare trade-offs; they are not probabilities. Demo data is illustrative, not a provider quote.")
        report = {"assessment_id": st.session_state.assessment_id,
                  "created_at": st.session_state.assessment_created_at,
                  "requirements": st.session_state.assessment_requirements_snapshot,
                  "profiles": st.session_state.assessment_profiles_snapshot,
                  "result": result}
        st.download_button("Download assessment JSON", json.dumps(report, indent=2, allow_nan=False),
                           file_name="edgewise-assessment.json", mime="application/json", type="primary")
        back_assessment, understand, new_assessment = st.columns(3)
        if back_assessment.button("Back to Assessment"):
            go("Infrastructure Assessment"); st.rerun()
        if understand.button("Understand the Decision", type="primary"):
            st.session_state.reviewed = True
            go("Decision Explanation"); st.rerun()
        if new_assessment.button("Start New Assessment"):
            st.session_state.assessment = None
            st.session_state.assessment_id = None
            st.session_state.assessment_created_at = None
            st.session_state.assessment_requirements_snapshot = None
            st.session_state.assessment_profiles_snapshot = None
            st.session_state.assessment_outdated = False
            st.session_state.reviewed = st.session_state.understood = False
            st.session_state.explanation_generated_for_assessment_id = None
            go("Application Requirements"); st.rerun()

elif page == "Decision Explanation":
    heading("Step 5 of 5", "Decision explanation", "The structured engine result remains authoritative; explanation text cannot change scores, statuses, constraints, ranking, or recommendation.")
    result = current_result()
    if result is None:
        if has_outdated_result():
            st.warning("The previous result is outdated. Reassess the current inputs to generate a reliable explanation.")
        else:
            st.info("Run a current assessment to see its explanation.")
        if st.button("Go to assessment", type="primary"):
            go("Infrastructure Assessment"); st.rerun()
    else:
        if (st.session_state.decision_explanation is None
                or st.session_state.decision_explanation.get("assessment_id") != st.session_state.assessment_id):
            explanation = explain_decision(st.session_state.assessment_requirements_snapshot, result)
            st.session_state.decision_explanation = {
                "assessment_id": st.session_state.assessment_id,
                "text": explanation.text,
                "source": explanation.source,
            }
            st.session_state.explanation_generated_for_assessment_id = st.session_state.assessment_id
            st.session_state.understood = True
            st.rerun()
        explanation = DecisionExplanation(
            text=st.session_state.decision_explanation["text"],
            source=st.session_state.decision_explanation["source"],
        )
        st.markdown(
            '<div class="soft-card"><div class="eyebrow">' + escape(explanation.source)
            + '</div><h3>Decision summary</h3><p>' + escape(explanation.text) + '</p></div>',
            unsafe_allow_html=True,
        )
        if result["recommendation"]:
            selected = next(tier for tier in result["tiers"] if tier["tier"] == result["recommendation"])
            st.subheader("Why this recommendation was selected")
            st.write(f"{TIER_LABELS[result['recommendation']]} is the engine's highest-ranked feasible tier. Its actual suitability score is {selected['score']:.2f}/100.")
        else:
            st.subheader("Why there is no recommendation")
            st.write("The decision engine found no tier with confirmed feasibility. See each tier's actual status and constraint evidence below.")
        st.subheader("Constraint evaluation, unknowns, and score details")
        for tier in result["tiers"]:
            with st.expander(f"{TIER_LABELS[tier['tier']]} · {tier['status']}"):
                for con in tier["constraints"]:
                    actual = "Unknown" if con["actual"] is None else con["actual"]
                    required = "Not applicable" if con["required"] is None else con["required"]
                    st.write(f"**{con['constraint']} · {con['status']}** — {con['reason']} (actual: {actual}; required: {required})")
                if tier["score_breakdown"]:
                    breakdown = tier["score_breakdown"]
                    st.dataframe(pd.DataFrame([{"Factor": name.replace("_", " ").title(), "Weight": factor["weight"], "Normalized utility": factor["normalized_value"], "Weighted points": factor["weighted_points"]} for name, factor in breakdown.items() if name != "total_score"]), hide_index=True, use_container_width=True)
        st.subheader("Deterministic assessment explanation")
        st.markdown(explain_assessment(result, include_details=True))
        st.write("The local explanation is always available. Optional Qualcomm AI text adds explanatory language only; feasibility, scores, ranking, and recommendation come from the local decision engine.")
        st.subheader("Feasible alternatives")
        alternatives = [row for row in result["ranking"] if row["tier"] != result["recommendation"]]
        if alternatives:
            st.dataframe(pd.DataFrame([{"Rank": row["rank"], "Tier": TIER_LABELS[row["tier"]], "Score": row["score"]} for row in alternatives]), hide_index=True, use_container_width=True)
        else:
            st.caption("No additional feasible alternatives are available.")
        with st.expander("How to read this result", expanded=False):
            st.write("First, EdgeWise checks latency, required onsite residency, minimum compute, bandwidth, and monthly cost. Any known failure makes a tier infeasible. Missing or invalid capability data leaves it unverified unless another known failure already makes it infeasible.")
            st.write("Only tiers that pass every applicable hard constraint receive the approved weighted suitability score and appear in the ranking. A score is a comparison aid, not a probability of success.")
        st.checkbox("I understand this decision and its trade-offs", key="understood")
        st.success("Decision explanation generated for this assessment.")
        back_results, back_dashboard = st.columns(2)
        with back_results:
            if st.button("Back to Results"):
                go("Placement Results"); st.rerun()
        with back_dashboard:
            if st.button("Return to Dashboard"):
                go("Dashboard"); st.rerun()
