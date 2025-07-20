# AGENTS.MD for Budgify

This file provides instructions and guidelines for the AI agent working on this repository. Please adhere to these guidelines to ensure consistency and quality.

## 🚀 Overview

This project is a professional, extensible command-line tool for importing, categorizing, and exporting credit-card transactions into a unified monthly ledger or Google Sheets workbook. The primary goal is to centralize financial data across multiple banks and formats.

The agent's primary responsibilities in this project include:
- Assisting with feature development
- Writing and refactoring code
- Fixing bugs
- Writing tests
- Improving documentation

## 📂 Project Structure

The repository is organized as follows:

- `transaction_tracker/`: Contains the main source code for the application.
  - `core/`: Core logic and data models.
  - `loaders/`: Modules for loading transactions from different banks.
  - `outputs/`: Modules for exporting transactions to different formats.
  - `ai/`: Modules for interacting with large language models.
- `tests/`: Contains all the tests for the project.
- `examples/`: Contains example configuration files.
- `data/`: Default local output dir for CSV.

When adding new files, please follow the existing directory structure.

## 💻 Coding Conventions

### General

- Follow the existing coding style.
- Write clear, concise, and well-documented code.
- Keep functions and methods small and focused on a single task.
- Use meaningful names for variables, functions, and classes.

### Python

- Follow the PEP 8 style guide.
- Use a linter like `flake8` or `pylint` to check for style issues.
- Use type hints for function signatures.

## 🧪 Testing

- All new features must be accompanied by tests.
- All bug fixes must include a regression test.
- Run the test suite before submitting any changes.

To run the tests, use the following command:

```bash
pytest -q
```

## ✅ Dos and ❌ Don'ts

### Dos

- **Do** communicate clearly and ask for clarification if the instructions are unclear.
- **Do** follow the project's conventions and guidelines.
- **Do** write tests for your code.
- **Do** update the documentation when you make changes.

### Don'ts

- **Don't** introduce new dependencies without approval.
- **Don't** make breaking changes without a major version bump.
- **Don't** commit directly to the `main` branch.
