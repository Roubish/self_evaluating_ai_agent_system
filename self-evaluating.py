from agent_system import run_agent


if __name__ == "__main__":
    query = input("Enter your query: ")
    run = run_agent(query)
    print(run["report"])
