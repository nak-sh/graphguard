import streamlit as st
import requests
import json

API_URL = "http://localhost:8000/api"

st.set_page_config(page_title="GraphGuard", layout="wide")
st.title("🛡️ GraphGuard: Investigation Workspace")
st.markdown("Autonomous, evidence-grounded fraud investigation agent.")

# --- 1. Sidebar: Alert Queue ---
st.sidebar.header("Alert Queue")
alert_options = {
    "A-104": "🚨 ALERT-104 (High Priority)",
    "D-201": "ℹ️ ALERT-D201 (Low Priority - Decoy)"
}
selected_entity = st.sidebar.selectbox("Select Entity to Investigate", options=list(alert_options.keys()), format_func=lambda x: alert_options[x])

if st.sidebar.button(f"Investigate {selected_entity}", type="primary"):
    with st.spinner("Agent is running graph queries and scoring evidence..."):
        alert_id = "ALERT-104" if selected_entity == "A-104" else "ALERT-D201"
        res = requests.post(f"{API_URL}/investigate", json={"alert_id": alert_id, "entity_id": selected_entity})
        if res.status_code == 200:
            st.session_state["investigation"] = res.json()
        else:
            st.sidebar.error("Backend API Error. Is FastAPI running?")

# --- 2. Main Workspace ---
if "investigation" in st.session_state:
    data = st.session_state["investigation"]
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Evidence & Findings")
        st.write(f"**Score:** {data['score']} / 100")
        st.write(f"**Tier:** `{data['tier']}`")
        
        st.markdown("### Agent Narrative")
        for finding in data['findings']:
            st.markdown(f"- {finding}")
            
        st.markdown("### Raw Graph Evidence")
        st.json(data['evidence_items'], expanded=False)

    with col2:
        st.subheader("Action Plan & Policy Gate")
        
        if data["dry_run_diff"]:
            st.warning("⚠️ Action Proposed")
            st.write("**Dry-Run Diff (FalkorDB Node Preview):**")
            st.json(data["dry_run_diff"])
            
            if st.button("Approve & Execute Hold", type="primary"):
                with st.spinner("Executing secure graph mutation..."):
                    action_payload = {
                        "target_entity": selected_entity,
                        "type": data["proposed_actions"][0]["type"]
                    }
                    exec_res = requests.post(f"{API_URL}/actions/execute", json=action_payload).json()
                    
                    if exec_res.get("success"):
                        st.success(f"Hold Applied! FalkorDB Verified Status: {exec_res['verified_status']}")
                        st.session_state["audit_id"] = exec_res["audit_id"]
                        st.info(f"Audit Node Created: {exec_res['audit_id']}")
                    else:
                        st.error("Execution failed.")
        else:
            st.success("No Action Required. Decoy respected.")
            
        # --- Rollback Feature ---
        if "audit_id" in st.session_state:
            st.markdown("---")
            st.subheader("Undo Action")
            if st.button("Rollback to Previous State"):
                with st.spinner("Restoring FalkorDB state..."):
                    rollback_res = requests.post(f"{API_URL}/actions/rollback", json={"audit_id": st.session_state["audit_id"]}).json()
                    if rollback_res.get("success"):
                        st.success(f"Rollback Complete! Node Status restored to: {rollback_res['verified_status']}")
                        del st.session_state["audit_id"]

                        