# Skill: Code Review

## Description
Performs a structured code review of the current branch changes compared to a base branch (default: `main`). The review follows the project's coding standards and best practices defined in [`AGENTS.md`](AGENTS.md).

## Parameters
- `base_branch` (optional): The branch to compare against. Default: `main`.
- `scope` (optional): Limit review to specific paths (e.g., `src/communicate/`). Default: all changed files.

## Workflow

### 1. Determine the diff
Run `git merge-base HEAD <base_branch>` to find the merge base, then `git diff <merge_base>..HEAD` to get the list of changed files and the full diff.

If `scope` is specified, filter the diff to only include files under that path.

### 2. Run pre-checks
Before reviewing the code manually, run the automated checks that the project requires:

```bash
# Lint checking (ruff)
make lint-check

# Type checking (mypy)
make mypy

# Tests
make test
```

If any of these fail, report the failures as blocking issues.

### 3. Review checklist

Go through each changed file and evaluate against the following checklist.

#### 3.1. Project-specific rules (from AGENTS.md)

- [ ] **Python 3.12+**: Code uses modern Python syntax (type hints, pattern matching, etc.)
- [ ] **Type annotations**: All functions/methods are fully type-annotated (`mypy` strict mode compatible)
- [ ] **Ruff formatting**: Code follows `ruff` style (line length 120, single quotes)
- [ ] **SQLAlchemy 1.4 Core**: DB access uses SQLAlchemy Core, not ORM
- [ ] **Pydantic v2**: Data models and validation use Pydantic v2
- [ ] **Imports at top**: All `import`/`from` statements are at the top of the file (PEP 8). No imports inside functions, except for the documented circular dependency exception in `_dependencies/`
- [ ] **Minimal comments**: No section-separator comments (`# ─── Section ───`). Only add comments where logic genuinely needs explanation (non-obvious edge cases, API quirks, design rationale). Module-level docstrings are fine
- [ ] **Schema changes**: If tables were modified, check that [`tests/tools/db.sql`](tests/tools/db.sql) and [`tests/factories/db_models.py`](tests/factories/db_models.py) are updated accordingly
- [ ] **Tests added**: New features include tests in [`tests/`](tests/). Tests use unique values (e.g., `random.randint()` or `uuid`) to avoid collisions with stale data
- [ ] **`make requirements` updated**: If dependencies changed, `requirements.txt` for affected functions is updated
- [ ] **No `.env`/secrets exposure**: No hardcoded credentials, no accidental `.env` file reads

#### 3.2. General code quality

- [ ] **Single responsibility**: Each function/class has one clear responsibility (serverless function pattern)
- [ ] **No dead code**: No commented-out code blocks, no unused imports/variables
- [ ] **Error handling**: External calls (DB, HTTP, API) have proper error handling, retries where appropriate
- [ ] **Logging**: Meaningful log messages (not just debug noise). Uses JSON logging setup from `yandex_tools.py` where applicable
- [ ] **No magic numbers/strings**: Constants are named properly
- [ ] **No global variables**: never use `global` variables. If you want to make signleton, use `@cache` decorator.
- [ ] **Async correctness**: If async code is used, proper `await`/event loop management
- [ ] **Security**: Input validation, no SQL injection (parameterized queries), no command injection

#### 3.3. Architecture & design

- [ ] **Serverless mindset**: Function follows the message-queue-driven pipeline pattern (no direct cross-function calls)
- [ ] **Locking**: If the function is in the notification pipeline (`compose_notifications`, `send_notifications`), it uses [`lock_manager`](src/_dependencies/lock_manager.py) to prevent parallel execution
- [ ] **Pub/sub**: Communication with other functions goes through YMQ topics (see [`pubsub.py`](src/_dependencies/pubsub.py))
- [ ] **Config**: New configuration values go through [`AppConfig`](src/_dependencies/commons.py) (pydantic-settings, env vars), not hardcoded
- [ ] **DB schema compatibility**: Changes are backward-compatible with existing data in production

#### 3.4. Testing

- [ ] **Tests pass**: `make test` passes
- [ ] **Test coverage**: New logic is covered by tests (happy path + edge cases)
- [ ] **Test isolation**: Tests don't depend on each other, use unique data values
- [ ] **No test pollution**: Tests clean up after themselves or use unique IDs

### 4. Compose the review report

Structure the report as follows:

```
## Code Review: <branch_name> → <base_branch>

### Summary
- Files changed: N
- Insertions: +N, Deletions: -N
- Blocking issues: N
- Warnings: N
- Suggestions: N

### Pre-check results
- `make lint`: ✅ / ❌ (details)
- `make mypy`: ✅ / ❌ (details)
- `make test`: ✅ / ❌ (details)

### Issues found

#### 🔴 Blocking (must fix before merge)
1. **Description** — file:line — explanation
2. ...

#### 🟡 Warnings (should fix)
1. **Description** — file:line — explanation
2. ...

#### 🔵 Suggestions (optional improvements)
1. **Description** — file:line — explanation
2. ...

### Overall verdict
✅ Approved / ❌ Changes requested / ⚠️ Approved with comments
```
