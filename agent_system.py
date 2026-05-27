import ast
import logging
import operator
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
MAX_REVISIONS = 3

load_dotenv(BASE_DIR / ".env")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / "system.log"),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

_llm: Optional[ChatGroq] = None


class AgentState(TypedDict, total=False):
    query: str
    plan: str
    final_response: str
    action_trace: List[Dict[str, Any]]
    behavior_feedback: str
    reasoning_feedback: str
    reviewer_feedback: str
    worker_calls: int
    reviewer_calls: int
    revisions: int
    tool_usage: int
    recommended_tool: str


def get_groq_api_key() -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if api_key:
        return api_key

    try:
        import streamlit as st

        api_key = st.secrets.get("GROQ_API_KEY")
    except Exception:
        api_key = None

    if api_key:
        api_key = str(api_key)
        os.environ["GROQ_API_KEY"] = api_key
        return api_key

    raise RuntimeError(
        "Missing GROQ_API_KEY. Add it to .env locally or to Streamlit Cloud secrets before running the app."
    )


def get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        get_groq_api_key()
        _llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    return _llm


def search_tool(query: str) -> str:
    logging.info("Search tool called: %s", query)
    return f"Search result for '{query}': [simulated factual info]"


ARITHMETIC_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def evaluate_arithmetic(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in ARITHMETIC_OPERATORS:
        left = evaluate_arithmetic(node.left)
        right = evaluate_arithmetic(node.right)
        return ARITHMETIC_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPERATORS:
        return UNARY_OPERATORS[type(node.op)](evaluate_arithmetic(node.operand))
    raise ValueError("Only simple arithmetic expressions are allowed.")


def code_tool(code: str) -> str:
    logging.info("Code tool executed: %s", code)
    try:
        expression = code.strip().strip("`")
        parsed = ast.parse(expression, mode="eval")
        exec_result = evaluate_arithmetic(parsed.body)
        return str(exec_result)
    except Exception:
        return "Code execution result: [simulated]"


def db_tool(query: str) -> str:
    logging.info("DB tool called: %s", query)
    return f"DB query result for '{query}': [simulated data]"


tools = {"search": search_tool, "code": code_tool, "db": db_tool}


def write_to_file(filename: str, content: str):
    with open(LOG_DIR / filename, "w", encoding="utf-8") as f:
        f.write(content)


def clean_markdown_label(line: str) -> str:
    return line.strip().replace("**", "").strip()


def extract_final_answer(response: str) -> str:
    match = re.search(r"(?is)\bfinal\s+answer\s*(?:is)?\s*:\s*(.+)$", response)
    if match:
        return match.group(1).strip()
    return response.strip() or "No final answer found."


def find_action_input(lines: List[str], start_index: int, fallback: str) -> str:
    for next_line in lines[start_index + 1:]:
        stripped = clean_markdown_label(next_line)
        if not stripped:
            continue
        input_match = re.match(r"(?i)^(?:action\s+input|input|search|code|db)\s*:\s*(.+)$", stripped)
        if input_match:
            return input_match.group(1).strip()
        if stripped.lower().startswith(("thought:", "action:", "final answer")):
            break
    return fallback


def parse_actions(response: str) -> List[Dict[str, str]]:
    action_trace = []
    lines = response.splitlines()

    for index, line in enumerate(lines):
        action_match = re.match(r"(?i)^action\s*:\s*(.+)$", clean_markdown_label(line))
        if not action_match:
            continue

        action_text = action_match.group(1).strip()
        tool_name = next((name for name in tools if re.search(rf"\b{name}\b", action_text, re.I)), None)
        if not tool_name:
            continue

        action_input = find_action_input(lines, index, action_text)
        result = tools[tool_name](action_input)
        action_trace.append({"tool": tool_name, "input": action_input, "result": result})

    return action_trace


def is_approved(feedback: str) -> bool:
    text = feedback.lower()
    decision = re.search(r"\bdecision\s*:\s*(approve|revise)\b", text)
    if decision:
        return decision.group(1) == "approve"
    if re.search(r"\b(should\s+revise|needs?\s+revision|decision\s*:\s*revise|not\s+approve|cannot\s+approve)\b", text):
        return False
    if re.search(r"\bapprove\s*:\s*yes\b", text):
        return True
    return bool(re.search(r"\bapprove\b|\bapproved\b", text))


def recommend_tool(query: str) -> str:
    text = query.lower()
    if re.search(r"\b(calculate|compute|math|price|discount|total|sum|multiply|divide|percent|percentage)\b", text):
        return "code"
    if re.search(r"\d+\s*[-+*/%^]\s*\d+", text):
        return "code"
    if re.search(r"\b(database|db|sql|table|record|records|row|rows|stored data|users|orders)\b", text):
        return "db"
    if re.search(r"\b(search|find|lookup|look up|latest|current|fact|facts)\b", text):
        return "search"
    return "none"


def planner(state: AgentState) -> AgentState:
    prompt = f"Create a short plan to solve: {state['query']}"
    plan = get_llm().invoke(prompt).content
    state["plan"] = plan
    write_to_file("plan.txt", plan)
    return state


def worker(state: AgentState) -> AgentState:
    state["worker_calls"] = state.get("worker_calls", 0) + 1
    recommended_tool = recommend_tool(state["query"])
    state["recommended_tool"] = recommended_tool
    feedback = (
        f"Behavior: {state.get('behavior_feedback', '')}\n"
        f"Reasoning: {state.get('reasoning_feedback', '')}\n"
        f"Reviewer: {state.get('reviewer_feedback', '')}"
    )
    prompt = f"""
    Query: {state['query']}
    Plan: {state['plan']}
    Feedback: {feedback}

    Available tools: search, code, db.
    Recommended tool for this query: {recommended_tool}
    If the recommended tool is search, code, or db, use that Action unless the feedback clearly says it is wrong.
    Use Action: code for arithmetic, math, formulas, or small calculations.
    Use Action: search when the answer needs factual lookup or simulated factual context.
    Use Action: db when the user asks about records, tables, stored data, or database-like queries.
    Use Action: none only when the task is already answerable without a tool, such as short explanations, writing, or brainstorming.
    Do not invent tool results.
    Use this exact format:
    Thought: your reasoning
    Action: search/code/db or none
    Action Input: input for the selected tool
    Final Answer: direct answer to the user
    """
    response = get_llm().invoke(prompt).content
    write_to_file("worker_output.txt", response)

    action_trace = parse_actions(response)
    final_answer = extract_final_answer(response)

    state["final_response"] = final_answer
    state["action_trace"] = action_trace
    state["tool_usage"] = state.get("tool_usage", 0) + len(action_trace)
    return state


def behavior_evaluator(state: AgentState) -> AgentState:
    prompt = f"""
    Query: {state['query']}
    Action Trace: {state['action_trace']}
    Evaluate behavior: tool usage, efficiency, correctness.
    Return exactly:
    Score: 0-10
    Decision: approve or revise
    Explanation: short reason
    """
    eval_resp = get_llm().invoke(prompt).content
    state["behavior_feedback"] = eval_resp
    write_to_file("behavior_eval.txt", eval_resp)
    return state


def reasoning_evaluator(state: AgentState) -> AgentState:
    prompt = f"""
    Query: {state['query']}
    Response: {state['final_response']}
    Evaluate reasoning quality.
    Return exactly:
    Score: 0-10
    Decision: approve or revise
    Explanation: short reason
    """
    eval_resp = get_llm().invoke(prompt).content
    state["reasoning_feedback"] = eval_resp
    write_to_file("reasoning_eval.txt", eval_resp)
    return state


def reviewer(state: AgentState) -> AgentState:
    state["reviewer_calls"] = state.get("reviewer_calls", 0) + 1
    prompt = f"""
    Final Answer: {state['final_response']}
    Evaluate output quality.
    Return exactly:
    Score: 0-10
    Decision: approve or revise
    Explanation: short reason
    """
    eval_resp = get_llm().invoke(prompt).content
    state["reviewer_feedback"] = eval_resp
    write_to_file("reviewer_eval.txt", eval_resp)
    return state


def router(state: AgentState):
    if (
        is_approved(state.get("behavior_feedback", ""))
        and is_approved(state.get("reasoning_feedback", ""))
        and is_approved(state.get("reviewer_feedback", ""))
    ):
        return END
    if state.get("revisions", 0) >= MAX_REVISIONS:
        return END
    return "revise"


def record_revision(state: AgentState) -> AgentState:
    state["revisions"] = state.get("revisions", 0) + 1
    return state


def system_score(state: AgentState, exec_time: float) -> int:
    score = 10
    if exec_time > 10:
        score -= 2
    if state.get("revisions", 0) > 2:
        score -= 2
    if state.get("tool_usage", 0) > 6:
        score -= 2
    if state.get("worker_calls", 0) > 3:
        score -= 2
    return max(0, score)


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner)
    graph.add_node("worker", worker)
    graph.add_node("behavior", behavior_evaluator)
    graph.add_node("reasoning", reasoning_evaluator)
    graph.add_node("reviewer", reviewer)
    graph.add_node("revise", record_revision)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "worker")
    graph.add_edge("worker", "behavior")
    graph.add_edge("behavior", "reasoning")
    graph.add_edge("reasoning", "reviewer")
    graph.add_edge("revise", "worker")
    graph.add_conditional_edges("reviewer", router, {"revise": "revise", END: END})
    return graph.compile()


app = build_graph()


def build_report(
    result: AgentState,
    exec_time: float,
    score: int,
    username: Optional[str] = None,
    user_email: Optional[str] = None,
) -> str:
    lines = []
    if username and user_email:
        lines.extend([f"User: {username}", f"Email: {user_email}"])
    lines.extend(
        [
            f"Final Answer: {result.get('final_response', 'No final answer found.')}",
            f"Execution Time: {exec_time:.2f}s",
            f"Worker Calls: {result.get('worker_calls')}",
            f"Revisions: {result.get('revisions')}",
            f"Tool Usage: {result.get('tool_usage')}",
            f"System Score: {score}/10",
        ]
    )
    return "\n".join(lines) + "\n"


def run_agent(query: str, username: Optional[str] = None, user_email: Optional[str] = None) -> Dict[str, Any]:
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("Please enter a query before running the agent.")

    initial_state: AgentState = {
        "query": clean_query,
        "worker_calls": 0,
        "tool_usage": 0,
        "revisions": 0,
        "reviewer_calls": 0,
    }

    start = time.time()
    result = app.invoke(initial_state)
    exec_time = time.time() - start
    score = system_score(result, exec_time)
    report = build_report(result, exec_time, score, username, user_email)
    write_to_file("final_report.txt", report)

    return {
        "state": result,
        "execution_time": exec_time,
        "score": score,
        "report": report,
    }
