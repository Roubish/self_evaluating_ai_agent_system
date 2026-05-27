# Self-Evaluating AI Agent System

This project is a simple self-evaluating AI agent built with LangGraph and Groq. The agent answers a user query, evaluates its own behavior and reasoning, asks a reviewer to check the final output, and revises the answer when the evaluators request changes.

## Live App

Open the deployed Streamlit app here:

https://selfevaluatingaiagentsystem-utdjoyrt5tzypderunqcr5.streamlit.app/

## What This Project Does

The system runs a small multi-step agent workflow:

1. The user enters a query.
2. The planner creates a short plan.
3. The worker generates an answer and may use simulated tools.
4. The behavior evaluator checks tool usage, efficiency, and correctness.
5. The reasoning evaluator checks the quality of the answer logic.
6. The reviewer checks final output quality.
7. The router either finishes or sends the answer back for revision.
8. The app shows the tools used, saves the latest report, and keeps the last 5 query results in the Streamlit session history.

## Workflow

```text
User Query
   |
   v
Planner
   |
   v
Worker
   |
   v
Behavior Evaluator
   |
   v
Reasoning Evaluator
   |
   v
Reviewer
   |
   v
Router
   |
   +--> Approved --> Final Report
   |
   +--> Revise --> Worker
```

## Project Structure

```text
self_evaluating_ai_agent_system/
├── agent_system.py         # Shared LangGraph workflow and run_agent helper
├── streamlit_app.py        # Streamlit login and agent UI
├── self-evaluating.py      # CLI runner for the agent system
├── DEPLOYMENT.md           # Streamlit deployment guide
├── README.md               # Project documentation
├── requirements.txt        # Python dependencies
├── .env.example            # Example environment file
├── .gitignore              # Files to ignore in GitHub
└── logs/                   # Generated runtime outputs
    ├── plan.txt
    ├── worker_output.txt
    ├── behavior_eval.txt
    ├── reasoning_eval.txt
    ├── reviewer_eval.txt
    ├── final_report.txt
    └── system.log
```

## Main Code Summary

### `AgentState`

`AgentState` is the shared state passed between LangGraph nodes. It stores the query, plan, final response, evaluator feedback, recommended tool, revision count, tool usage count, and call counts.

### Simulated Tools

The project includes three simple tools:

- `search_tool`: returns simulated search results.
- `code_tool`: safely evaluates simple arithmetic expressions.
- `db_tool`: returns simulated database results.

These tools are not connected to real search or database services yet. They are placeholders for learning the agent workflow.

The worker also recommends a tool from the query text:

- arithmetic or calculation tasks use `code`
- database-style tasks use `db`
- lookup or fact-style tasks use `search`
- simple writing or explanation tasks can use `none`

### Planner

The planner receives the user query and creates a short plan using the Groq LLM.

### Worker

The worker uses the plan and evaluator feedback to generate a final answer. It follows this format:

```text
Thought: reasoning
Action: search/code/db or none
Action Input: input for the selected tool
Final Answer: direct answer to the user
```

The code parses the worker output, extracts the final answer, and records any tool usage.

### Evaluators

The system has three evaluator nodes:

- `behavior_evaluator`: checks tool usage and correctness.
- `reasoning_evaluator`: checks reasoning quality.
- `reviewer`: checks the final answer quality.

Each evaluator returns:

```text
Score: 0-10
Decision: approve or revise
Explanation: short reason
```

### Router

The router checks evaluator decisions. If all evaluators approve, the graph ends. If any evaluator asks for revision, the system loops back to the worker. The maximum revision limit is controlled by:

```python
MAX_REVISIONS = 3
```

### System Score

The final score starts at 10 and subtracts points for slow execution, too many revisions, high tool usage, or too many worker calls.

## Setup Steps

### 1. Clone the repository

```bash
git clone https://github.com/Roubish/self_evaluating_ai_agent_system.git
cd self_evaluating_ai_agent_system
```

If you are already inside this project folder, just open a terminal in:

```bash
self_evaluating_ai_agent_system
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

On Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create your `.env` file

Copy the example file:

```bash
cp .env.example .env
```

Then add your Groq API key:

```text
GROQ_API_KEY=your_groq_api_key_here
```

Do not upload your real `.env` file to GitHub.

### 5. Run the project

```bash
python3 self-evaluating.py
```

The program will ask:

```text
Enter your query:
```

Example query:

```text
Explain what LangGraph is in simple words
```

### 6. Run the Streamlit app

```bash
streamlit run streamlit_app.py
```

The Streamlit app opens with a login screen. Enter a username and email, generate the development verification code, verify it, then ask your question from the welcome screen. The app shows the final answer, plan, tool calls, evaluator feedback, report, and last 5 history items.

## Deployment

Deploy with `streamlit_app.py` as the app entrypoint. Add `GROQ_API_KEY` as a deployment secret, not in your repository.

Full deployment steps are in [`DEPLOYMENT.md`](DEPLOYMENT.md).

After deploying from GitHub, update the live app by committing your changes and running:

```bash
git push origin main
```

## Example Queries

```text
Explain what LangGraph is in simple words
```

```text
What is the final price of a $1000 product after a 10% discount?
```

```text
Write a short Python function to check if a number is even or odd
```

```text
Explain RAG in simple words with one example
```

```text
Make a 5-step study plan to learn LangChain and LangGraph
```

## Example Output

```text
Final Answer: LangGraph is a framework for building AI workflows as graphs. Each step is a node, and the connections between steps are edges.
Execution Time: 12.45s
Worker Calls: 1
Revisions: 0
Tool Usage: 0
System Score: 8/10
```

## Logs

After each run, the system saves outputs inside the `logs/` folder:

- `plan.txt`: planner output
- `worker_output.txt`: worker output
- `behavior_eval.txt`: behavior evaluator feedback
- `reasoning_eval.txt`: reasoning evaluator feedback
- `reviewer_eval.txt`: reviewer feedback
- `final_report.txt`: final printed report
- `system.log`: tool and system activity logs

## Updating GitHub

From inside `self_evaluating_ai_agent_system`, run:

```bash
git add .
git commit -m "Describe your change"
git push origin main
```

Important: make sure `.env` is not committed. This project includes `.gitignore` to protect it. Use Streamlit Cloud secrets for `GROQ_API_KEY`.

## Notes

- The search and database tools are simulated.
- The code tool only supports simple arithmetic expressions.
- The Streamlit history keeps the last 5 results in the current browser session.
- Email verification is development-only and does not send a real email.
- The evaluator decisions are text-based, so structured JSON output would be a good future improvement.
- This project is useful for learning LangGraph agent loops, evaluator agents, revision routing, and logging.

## Future Improvements

- Use real web search instead of simulated search.
- Connect a real database tool.
- Use structured evaluator outputs with JSON or Pydantic.
- Add unit tests for answer parsing and router decisions.
- Move model name and revision limit into environment variables.
