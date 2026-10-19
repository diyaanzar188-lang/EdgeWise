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
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; color:#252525; }
h1,h2,h3 { font-family:'Manrope',sans-serif; letter-spacing:-.035em; }
.block-container { max-width: 1280px; padding-top:2.2rem; padding-bottom:4rem; }
.eyebrow { color:#C65D3B; font-size:.75rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; margin-bottom:.5rem; }
.hero { background:#F8F8F7; border:1px solid #E7E5E4; border-radius:18px; padding:2.4rem; }
.hero h1 { font-size:3rem; margin:0 0 .8rem; }
.hero p { color:#686868; font-size:1.08rem; max-width:720px; }
.soft-card { background:#fff; border:1px solid #E7E5E4; border-radius:14px; padding:1.2rem 1.35rem; height:100%; }
.tier-name { color:#686868; font-size:.88rem; }
.metric-value { font-family:'Manrope',sans-serif; font-size:1.45rem; font-weight:700; margin-top:.25rem; }
.muted { color:#686868; }
[data-testid="stSidebar"] { background:#F8F8F7; border-right:1px solid #E7E5E4; }
div.stButton > button[kind="primary"] { background:#C65D3B; border-color:#C65D3B; }
div.stButton > button[kind="primary"]:hover { background:#a94e32; border-color:#a94e32; }
</style>
""", unsafe_allow_html=True)

PAGES = ["Home", "Dashboard", "Application Requirements", "Infrastructure Data Source",
         "Infrastructure Assessment", "Placement Results", "Decision Explanation"]
STEPS = ["Define Requirements", "Configure Infrastructure", "Run Assessment", "Review Recommendation", "Understand the Decision"]


def initialize_state():
    defaults = {
        "requirements": dict(DEFAULT_REQUIREMENTS), "profiles": get_demo_profiles(),
        "profiles_mode": "Demo profiles", "requirements_done": False, "profiles_done": False,
        "assessment": None, "assessment_outdated": False, "reviewed": False, "understood": False,
        "page_menu": "Home",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def go(page: str):
    st.session_state.page_menu = page


def status_chip(status: str):
    palette = {"FEASIBLE": ("#EAF3EA", "#315C38"), "INFEASIBLE": ("#F8EAE5", "#9C4128"), "UNVERIFIED": ("#F5F0E3", "#78601C")}
    bg, fg = palette.get(status, ("#F8F8F7", "#686868"))
    st.markdown(f'<span style="display:inline-block;padding:.3rem .65rem;border-radius:999px;background:{bg};color:{fg};font-size:.76rem;font-weight:700;letter-spacing:.04em">{status}</span>', unsafe_allow_html=True)


def current_result():
    return st.session_state.assessment if st.session_state.assessment and not st.session_state.assessment_outdated else None


def workflow():
    done = [st.session_state.requirements_done, st.session_state.profiles_done,
            current_result() is not None, st.session_state.reviewed and current_result() is not None,
            st.session_state.understood and st.session_state.reviewed and current_result() is not None]
    pages = ["Application Requirements", "Infrastructure Data Source", "Infrastructure Assessment", "Placement Results", "Decision Explanation"]
    current_step = next((i for i, finished in enumerate(done) if not finished), 4)
    st.markdown("#### Your workflow")
    cols = st.columns(5)
    for i, (col, title) in enumerate(zip(cols, STEPS)):
        mark = "✓" if done[i] else ("●" if i == current_step else "○")
        color = "#C65D3B" if i == current_step else ("#315C38" if done[i] else "#9A9691")
        col.markdown(f'<div style="border-top:2px solid {color};padding-top:.55rem;color:{color};font-size:.78rem;font-weight:700">{mark} &nbsp; {title}</div>', unsafe_allow_html=True)


def heading(kicker: str, title: str, subtitle: str = ""):
    st.markdown(f'<div class="eyebrow">{kicker}</div>', unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.markdown(f'<p class="muted">{subtitle}</p>', unsafe_allow_html=True)


def profile_errors(candidate):
    errors = []
    expected_tiers = set(TIER_ORDER)
    capability_fields = {"latency_ms", "data_stays_onsite", "compute", "bandwidth_mbps", "monthly_cost"}
    if not isinstance(candidate, Mapping):
        return ["Profiles must be a JSON object keyed by the four tier identifiers."]
    if set(candidate) != expected_tiers:
        errors.append("Include exactly these four tier keys: " + ", ".join(TIER_ORDER) + ".")
    for tier in TIER_ORDER:
        if tier not in candidate:
            continue
        profile = candidate[tier]
        if not isinstance(profile, Mapping):
            errors.append(f"{tier} must contain a capability object.")
            continue
        if set(profile) - capability_fields:
            errors.append(f"{tier} has unsupported fields: " + ", ".join(sorted(set(profile) - capability_fields)))
        if set(profile) - capability_fields:
            continue
        for field, value in profile.items():
            if value is None:
                continue
            if field in {"latency_ms", "bandwidth_mbps", "monthly_cost"}:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    errors.append(f"{tier}.{field} must be a finite nonnegative number or null.")
            elif field == "data_stays_onsite" and type(value) is not bool:
                errors.append(f"{tier}.{field} must be true, false, or null.")
            elif field == "compute" and value not in ("low", "medium", "high"):
                errors.append(f"{tier}.{field} must be low, medium, high, or null.")
    return errors


def profile_editor_frame(profiles):
    rows = []
    for tier in TIER_ORDER:
        row = {"tier": TIER_LABELS[tier], **profiles.get(tier, {})}
        for field in ("latency_ms", "data_stays_onsite", "compute", "bandwidth_mbps", "monthly_cost"):
            row.setdefault(field, None)
        rows.append(row)
    return pd.DataFrame(rows).set_index("tier")


def edited_frame_to_profiles(frame):
    reverse = {label: key for key, label in TIER_LABELS.items()}
    profiles = {}
    for label, row in frame.iterrows():
        tier = reverse.get(label)
        if tier is None:
            continue
        profiles[tier] = {field: (None if pd.isna(row[field]) else row[field].item() if hasattr(row[field], "item") else row[field])
                          for field in ("latency_ms", "data_stays_onsite", "compute", "bandwidth_mbps", "monthly_cost")}
    return profiles


initialize_state()

with st.sidebar:
    st.markdown("<div class='eyebrow'>EDGEWISE</div>", unsafe_allow_html=True)
    st.markdown("### Placement Advisor")
    st.caption("Intelligent infrastructure placement")
    st.divider()
    st.selectbox("Workspace", PAGES, key="page_menu", label_visibility="collapsed")
    st.divider()
    workflow()
    st.divider()
    st.caption("Decision engine runs locally. No AI service changes your placement result.")

page = st.session_state.page_menu
st.markdown('<div class="eyebrow">EDGEWISE / INTELLIGENT INFRASTRUCTURE PLACEMENT</div>', unsafe_allow_html=True)

if page == "Home":
    st.markdown("""<section class="hero"><div class="eyebrow">A clearer path to the right infrastructure</div>
    <h1>Place every workload<br>with a little more certainty.</h1>
    <p>Compare application requirements with On Device, Far Edge, Regional Edge, and Cloud infrastructure. EdgeWise checks hard constraints first, then ranks only the tiers that are confirmed feasible.</p></section>""", unsafe_allow_html=True)
    st.write("")
    left, right = st.columns([1, 1])
    with left:
        if st.button("Start assessment", type="primary", use_container_width=True):
            go("Application Requirements")
            st.rerun()
    with right:
        st.markdown("<div class='muted' style='padding:.65rem 0'>No assessment has been run in this session yet.</div>" if current_result() is None else "<div class='muted' style='padding:.65rem 0'>A current assessment is available in your results.</div>", unsafe_allow_html=True)
    st.subheader("Four infrastructure tiers")
    cols = st.columns(4)
    descriptions = ["Compute close to the workload", "Low-latency local infrastructure", "Shared infrastructure across a region", "Elastic, centralized infrastructure"]
    for col, tier, desc in zip(cols, TIER_ORDER, descriptions):
        col.markdown(f"<div class='soft-card'><div class='tier-name'>{TIER_LABELS[tier]}</div><div style='margin-top:.65rem'>{desc}</div></div>", unsafe_allow_html=True)

elif page == "Dashboard":
    heading("Workspace", "Assessment dashboard", "A live view of progress in this session.")
    done = [st.session_state.requirements_done, st.session_state.profiles_done, current_result() is not None,
            st.session_state.reviewed and current_result() is not None,
            st.session_state.understood and current_result() is not None]
    cols = st.columns(5)
    for col, step, finished in zip(cols, STEPS, done):
        col.metric(step, "Complete" if finished else "Not started")
    result = current_result()
    if result is None:
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
        if st.session_state.assessment_outdated:
            st.warning("Inputs changed after this run. Reassess to refresh the result.")

elif page == "Application Requirements":
    heading("Step 1 of 5", "Application requirements", "Set the workload limits that each infrastructure tier must satisfy.")
    req = st.session_state.requirements
    with st.form("requirements_form"):
        c1, c2 = st.columns(2)
        with c1:
            latency = st.number_input("Maximum latency (ms)", min_value=0.0, value=float(req["max_latency_ms"]), step=1.0)
            onsite = st.checkbox("Data must stay onsite", value=req["data_must_stay_onsite"])
            compute = st.selectbox("Minimum compute", ["low", "medium", "high"], index=["low", "medium", "high"].index(req["min_compute"]))
        with c2:
            bandwidth = st.number_input("Required bandwidth (Mbps)", min_value=0.0, value=float(req["required_bandwidth_mbps"]), step=5.0)
            cost = st.number_input("Maximum monthly cost", min_value=0.0, value=float(req["max_monthly_cost"]), step=10.0)
        submitted = st.form_submit_button("Save requirements", type="primary", use_container_width=True)
    if submitted:
        updated = {"max_latency_ms": latency, "data_must_stay_onsite": onsite, "min_compute": compute,
                   "required_bandwidth_mbps": bandwidth, "max_monthly_cost": cost}
        changed = updated != st.session_state.requirements
        st.session_state.requirements = updated
        st.session_state.requirements_done = True
        if changed and st.session_state.assessment is not None:
            st.session_state.assessment_outdated = True
            st.session_state.reviewed = st.session_state.understood = False
        st.success("Requirements saved.")
    st.caption("The form contains exactly the five supported requirement fields.")
    if st.button("Continue to infrastructure data", type="primary"):
        go("Infrastructure Data Source"); st.rerun()

elif page == "Infrastructure Data Source":
    heading("Step 2 of 5", "Infrastructure data source", "Use the illustrative profiles or provide capability data in the exact tier-keyed schema.")
    mode = st.radio("Profile source", ["Demo profiles", "Custom data"], horizontal=True,
                    index=0 if st.session_state.profiles_mode == "Demo profiles" else 1)
    if mode == "Demo profiles":
        st.info("Illustrative values only. These are not live provider measurements or quotes.")
        st.dataframe(profile_editor_frame(get_demo_profiles()), use_container_width=True)
        if st.button("Use demo profiles", type="primary"):
            changed = st.session_state.profiles != get_demo_profiles()
            st.session_state.profiles = get_demo_profiles()
            st.session_state.profiles_mode = mode
            st.session_state.profiles_done = True
            if changed and st.session_state.assessment is not None:
                st.session_state.assessment_outdated = True
                st.session_state.reviewed = st.session_state.understood = False
            st.success("Demo profiles applied.")
    else:
        st.caption("Set unknown capabilities to null or leave them blank. Extra fields are rejected.")
        editor = st.data_editor(profile_editor_frame(st.session_state.profiles), use_container_width=True,
                                num_rows="fixed", key="profile_editor",
                                column_config={"data_stays_onsite": st.column_config.CheckboxColumn("data_stays_onsite"),
                                               "compute": st.column_config.SelectboxColumn("compute", options=["low", "medium", "high"]),
                                               "latency_ms": st.column_config.NumberColumn("latency_ms", min_value=0),
                                               "bandwidth_mbps": st.column_config.NumberColumn("bandwidth_mbps", min_value=0),
                                               "monthly_cost": st.column_config.NumberColumn("monthly_cost", min_value=0)})
        uploaded = st.file_uploader("Import JSON file", type=["json"])
        default_json = json.dumps(st.session_state.profiles, indent=2, allow_nan=False)
        json_text = st.text_area("Or paste profiles as JSON", value=default_json, height=230)
        import_mode = st.radio("Apply from", ["Table editor", "JSON input"], horizontal=True)
        if uploaded is not None and st.button("Load uploaded JSON", key="load_upload"):
            try:
                json_text = uploaded.getvalue().decode("utf-8")
                st.session_state["json_upload_text"] = json_text
                st.rerun()
            except (UnicodeDecodeError, Exception) as exc:
                st.error(f"Could not read the uploaded JSON file: {exc}")
        if "json_upload_text" in st.session_state:
            json_text = st.session_state["json_upload_text"]
            st.text_area("Loaded JSON preview", value=json_text, height=180, disabled=True)
        if st.button("Validate and apply custom profiles", type="primary"):
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
                    st.session_state.pop("json_upload_text", None)
                    if changed and st.session_state.assessment is not None:
                        st.session_state.assessment_outdated = True
                        st.session_state.reviewed = st.session_state.understood = False
                    st.success("Custom profiles validated and applied.")
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                st.error(f"Could not parse profile data: {exc}")
    if st.button("Continue to assessment", type="primary"):
        go("Infrastructure Assessment"); st.rerun()

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
        if st.button("Run assessment", type="primary", use_container_width=True):
            st.session_state.assessment = evaluate_placement(st.session_state.requirements, st.session_state.profiles)
            st.session_state.assessment_outdated = False
            st.session_state.reviewed = st.session_state.understood = False
            st.success("Assessment complete. Results were calculated from the saved inputs.")
        if current_result() is not None and st.button("Review placement results"):
            go("Placement Results"); st.rerun()

elif page == "Placement Results":
    heading("Step 4 of 5", "Placement results", "Feasibility is determined by hard constraints. Only feasible tiers receive a score and rank.")
    result = current_result()
    if result is None:
        st.info("There is no current assessment yet. Run the engine after saving your requirements and infrastructure data.")
        if st.button("Go to assessment", type="primary"):
            go("Infrastructure Assessment"); st.rerun()
    elif not result["valid"]:
        st.error("The assessment inputs were rejected.")
        for error in result["errors"]: st.write(f"- {error}")
    else:
        if result["recommendation"]:
            selected = tier_result = next(t for t in result["tiers"] if t["tier"] == result["recommendation"])
            st.markdown(f"<div class='hero'><div class='eyebrow'>Recommended placement</div><h2>{TIER_LABELS[result['recommendation']]}</h2><p>Suitability score: <b>{selected['score']:.2f}/100</b> · feasibility confirmed</p></div>", unsafe_allow_html=True)
        else:
            st.warning("No recommendation: no tier has confirmed feasibility.")
        st.subheader("Tier comparison")
        rows = []
        for tier in result["tiers"]:
            profile = st.session_state.profiles[tier["tier"]]
            rows.append({"Tier": TIER_LABELS[tier["tier"]], "Status": tier["status"], "Latency (ms)": profile.get("latency_ms"),
                         "Onsite data": profile.get("data_stays_onsite"), "Compute": profile.get("compute"),
                         "Bandwidth (Mbps)": profile.get("bandwidth_mbps"), "Monthly cost": profile.get("monthly_cost"),
                         "Score": tier["score"], "Rank": next((x["rank"] for x in result["ranking"] if x["tier"] == tier["tier"]), None)})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.subheader("Constraint evidence")
        for tier in result["tiers"]:
            with st.expander(f"{TIER_LABELS[tier['tier']]} · {tier['status']}", expanded=tier["tier"] == result["recommendation"]):
                status_chip(tier["status"])
                for con in tier["constraints"]:
                    st.markdown(f"**{con['constraint']} — {con['status']}**  \n{con['reason']}  \nActual: `{con['actual']}` · Required: `{con['required']}`")
                if tier["score_breakdown"]:
                    st.markdown("**Suitability score breakdown**")
                    breakdown = tier["score_breakdown"]
                    st.dataframe(pd.DataFrame([{"Factor": name.replace("_", " ").title(), "Weight": factor["weight"],
                        "Normalized utility": factor["normalized_value"], "Weighted points": factor["weighted_points"]}
                        for name, factor in breakdown.items() if name != "total_score"]), hide_index=True, use_container_width=True)
                st.write("**Status reasons**")
                for reason in tier["reasons"]: st.write(f"- {reason}")
        st.caption("Suitability scores compare trade-offs; they are not probabilities. Demo data is illustrative, not a provider quote.")
        st.download_button("Download assessment JSON", json.dumps(result, indent=2, allow_nan=False),
                           file_name="edgewise-assessment.json", mime="application/json", type="primary")
        st.checkbox("I reviewed the feasibility and ranking", key="reviewed")
        if st.session_state.reviewed and st.button("Continue to decision explanation", type="primary"):
            go("Decision Explanation"); st.rerun()

elif page == "Decision Explanation":
    heading("Step 5 of 5", "Understand the decision", "A deterministic explanation generated from the structured assessment.")
    result = current_result()
    if result is None:
        st.info("Run a current assessment to see its explanation.")
        if st.button("Go to assessment", type="primary"):
            go("Infrastructure Assessment"); st.rerun()
    else:
        st.markdown(f"<div class='hero'><div class='eyebrow'>Decision summary</div><p style='color:#252525;font-size:1.1rem'>{explain_assessment(result)}</p></div>", unsafe_allow_html=True)
        st.subheader("How to read this result")
        st.write("First, EdgeWise checks latency, required onsite residency, minimum compute, bandwidth, and monthly cost. Any known failure makes a tier infeasible. Missing or invalid capability data leaves it unverified unless another known failure already makes it infeasible.")
        st.write("Only tiers that pass every applicable hard constraint receive the approved weighted suitability score and appear in the ranking. A score is a comparison aid, not a probability of success.")
        st.checkbox("I understand this decision and its trade-offs", key="understood")
        if st.session_state.understood:
            st.success("Decision review complete for this assessment.")
        if st.button("Back to results"):
            go("Placement Results"); st.rerun()

