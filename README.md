# MisterKnew

MisterKnew is a multi-agent desktop interface built with Python. It combines a supervisor that decomposes tasks with specialized workers for web browsing and operating system automation.

![Interface screenshot](img.png)

## Features
- **Supervisor agent** plans tasks and delegates work.
- **Web worker** uses Playwright to navigate pages and extract data.
- **OS worker** executes shell commands and writes Python scripts.
- **Operator** module manages managers and workers and routes messages.
- Designed around the LangChain ecosystem for tool integration.

## Installation
1. Install [Poetry](https://python-poetry.org/) if it is not already available.
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Set any required API keys (e.g. `OPENAI_API_KEY`) in an `.env` file or the environment.

## Usage
Launch the graphical interface:
```bash
poetry run python run.py
```

A small example script is provided:
```bash
poetry run python test.py
```

## Project structure
- `ai_agents/` – agent implementations and shared tools.
- `ai_agents_operator/` – the `Operator` class that coordinates agents.
- `communicator/` – messaging layer between agents.
- `utils/` – helpers and logging utilities.
- `run.py` – main entry point for the Tkinter UI.
- `test.py` – simple example for running an agent.

## Contributing
Issues and pull requests are welcome. Please ensure code is formatted and tests are added for new features.

