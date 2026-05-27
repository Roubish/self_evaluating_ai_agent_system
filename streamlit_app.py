import random
import re
from datetime import datetime

import streamlit as st

from agent_system import LOG_DIR, run_agent


EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match(email.strip()))


def init_session_state():
    defaults = {
        "authenticated": False,
        "username": "",
        "email": "",
        "verification_code": "",
        "verification_sent": False,
        "last_run": None,
        "last_query": "",
        "history": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def render_login():
    st.title("Self-Evaluating AI Agent")
    st.subheader("Login")

    username = st.text_input("Username", value=st.session_state.username, placeholder="Enter your username")
    email = st.text_input("Email", value=st.session_state.email, placeholder="name@example.com")

    send_code = st.button("Send verification code", use_container_width=True)
    if send_code:
        if not username.strip():
            st.error("Please enter a username.")
        elif not is_valid_email(email):
            st.error("Please enter a valid email address.")
        else:
            st.session_state.username = username.strip()
            st.session_state.email = email.strip()
            st.session_state.verification_code = f"{random.randint(100000, 999999)}"
            st.session_state.verification_sent = True
            st.success("Verification code generated.")

    if st.session_state.verification_sent:
        st.info(f"Development verification code: {st.session_state.verification_code}")
        entered_code = st.text_input("Verification code", max_chars=6)
        verify = st.button("Verify and login", type="primary", use_container_width=True)
        if verify:
            if entered_code.strip() == st.session_state.verification_code:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("The verification code is incorrect.")


def render_action_trace(action_trace):
    if not action_trace:
        st.write("No simulated tools were used.")
        return

    for index, action in enumerate(action_trace, start=1):
        with st.expander(f"Tool call {index}: {action.get('tool', 'unknown')}"):
            st.write(f"Input: {action.get('input', '')}")
            st.write(f"Result: {action.get('result', '')}")


def get_used_tools(action_trace):
    return [action.get("tool", "unknown") for action in action_trace]


def render_tool_summary(action_trace):
    tools = get_used_tools(action_trace)
    if not tools:
        st.info("Tools used: none")
        return

    st.success(f"Tools used: {', '.join(tools)}")


def save_history(run):
    state = run["state"]
    action_trace = state.get("action_trace", [])
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "query": state.get("query", ""),
        "answer": state.get("final_response", "No final answer found."),
        "tools": get_used_tools(action_trace),
        "score": run.get("score", 0),
        "execution_time": run.get("execution_time", 0),
        "revisions": state.get("revisions", 0),
    }
    st.session_state.history = [entry, *st.session_state.history][:5]


def render_history():
    history = st.session_state.history
    if not history:
        st.write("No history yet.")
        return

    for index, entry in enumerate(history, start=1):
        tools = ", ".join(entry["tools"]) if entry["tools"] else "none"
        with st.expander(f"{index}. {entry['query'][:80]}"):
            st.write(f"Time: {entry['time']}")
            st.write(f"Tools used: {tools}")
            st.write(f"Score: {entry['score']}/10")
            st.write(f"Execution: {entry['execution_time']:.2f}s")
            st.write(f"Revisions: {entry['revisions']}")
            st.markdown("**Answer**")
            st.write(entry["answer"])


def render_agent_app():
    st.title(f"Welcome, {st.session_state.username}")

    with st.sidebar:
        st.write("Logged in as")
        st.write(st.session_state.email)
        st.divider()
        st.write("Last 5 History")
        render_history()
        if st.session_state.history and st.button("Clear history", use_container_width=True):
            st.session_state.history = []
            st.rerun()
        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.verification_sent = False
            st.session_state.verification_code = ""
            st.session_state.last_run = None
            st.rerun()

    query = st.text_area(
        "Ask your question",
        value=st.session_state.last_query,
        height=130,
        placeholder="Example: Explain RAG in simple words with one example",
    )

    if st.button("Run self-evaluating agent", type="primary", use_container_width=True):
        with st.spinner("Running planner, worker, evaluators, reviewer, and router..."):
            try:
                st.session_state.last_query = query
                st.session_state.last_run = None
                st.session_state.last_run = run_agent(
                    query,
                    username=st.session_state.username,
                    user_email=st.session_state.email,
                )
                save_history(st.session_state.last_run)
            except Exception as exc:
                st.error(str(exc))

    run = st.session_state.last_run
    if not run:
        return

    state = run["state"]
    st.subheader("User Question")
    st.write(state.get("query", ""))

    st.subheader("Final Answer")
    st.write(state.get("final_response", "No final answer found."))
    render_tool_summary(state.get("action_trace", []))

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Score", f"{run['score']}/10")
    col2.metric("Execution", f"{run['execution_time']:.2f}s")
    col3.metric("Worker Calls", state.get("worker_calls", 0))
    col4.metric("Revisions", state.get("revisions", 0))

    tabs = st.tabs(["Plan", "Tools", "Evaluations", "Report", "History"])
    with tabs[0]:
        st.write(state.get("plan", "No plan found."))
    with tabs[1]:
        render_action_trace(state.get("action_trace", []))
    with tabs[2]:
        st.markdown("**Behavior Evaluator**")
        st.text(state.get("behavior_feedback", "No behavior feedback found."))
        st.markdown("**Reasoning Evaluator**")
        st.text(state.get("reasoning_feedback", "No reasoning feedback found."))
        st.markdown("**Reviewer**")
        st.text(state.get("reviewer_feedback", "No reviewer feedback found."))
    with tabs[3]:
        st.text(run["report"])
        st.caption(f"Saved to {LOG_DIR / 'final_report.txt'}")
    with tabs[4]:
        render_history()


def main():
    st.set_page_config(page_title="Self-Evaluating AI Agent", layout="wide")
    init_session_state()
    if st.session_state.authenticated:
        render_agent_app()
    else:
        render_login()


if __name__ == "__main__":
    main()
