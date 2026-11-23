# Python style

Applies to everything under `engine/`, `rl/`, `generator/`, `data/` and `tests/`.
`ruff` enforces most of it (`.\.venv\Scripts\python.exe -m ruff check .` and `ruff format .`).

## Basics
- Python 3.13, PEP 8, line length 120, double quotes. Imports sorted (ruff `I`).
- Standard library first. Ask before adding any dependency; dev-only tools go in `[project.optional-dependencies].dev`.
- `from __future__ import annotations` at the top of every module.

## Functional style with SOLID
The codebase uses plain functions over plain data. SOLID still applies, expressed through functions:

| Principle | How it applies here |
|---|---|
| **Single responsibility** | One function does one job: parse, *or* validate, *or* compute, *or* print/write. A function that both computes and prints is split. CLIs (`main`) only parse arguments and call other functions. |
| **Open/closed** | Extend by adding data (a new decision table, a new policy factory in `POLICIES`), not by editing the engine. |
| **Liskov substitution** | Anything with the same interface is interchangeable: every policy is an `rl.agents.Agent`; every LLM is a `(system, user, seed) -> str` function. |
| **Interface segregation** | Callers receive only what they use (a connection, a table, a function), not a whole object graph. |
| **Dependency inversion** | Dependencies are parameters: `random.Random`, the DB connection, the LLM function, the policy. No hidden globals except read-only caches (`functools.lru_cache`). |

Rules:
- No behavior classes. Data is `dict`, `NamedTuple`, `TypedDict`, or a frozen `@dataclass` with no methods
  (use the dataclass when a field must be hidden from `repr`, e.g. an API key). Exceptions are the only classes with behavior.
- Secrets (API keys) arrive as parameters or environment variables, never as command-line values; keep them out of
  `repr`, error messages, logs and output files.
- Pure functions by default. Side effects (I/O, network, printing, mutating a simulator student) live in clearly named functions (`save`, `print_*`, `answer`, `teach`) and are documented.
- DRY: shared logic gets one function; shared test setup goes in `tests/conftest.py`.
- Prefer returning values over mutating arguments; when a simulator function mutates its input for speed, say so in the docstring.

## Type hints
- Every function has parameter and return annotations, including private helpers.
- Use builtin generics (`list[str]`, `dict[str, int]`, `X | None`), `collections.abc.Callable`/`Iterator`.
- Name recurring shapes with aliases (`Table`, `Slots`, `Ctx`, `LLM`).

## Docstrings (Google style)
- Every module and every public function has a docstring. Private helpers (`_name`) get a one-line docstring when the name is not self-explanatory.
- First line: imperative summary ending with a period.
- Add `Args:`, `Returns:`, `Raises:` sections when a function has non-obvious parameters, return shape or errors.

```python
def score_gap(student_codes: list[str], correct_codes: list[str], con: Connection | None = None) -> dict:
    """Compare the risk score of the student's codes with the correct codes.

    Args:
        student_codes: ICD-10-CM codes the student picked.
        correct_codes: Codes from the rules engine.
        con: Code database; defaults to the shared read-only connection.

    Returns:
        Dict with `student`, `correct`, `gap`, `direction` ("over" | "under" | "none").
    """
```

## Errors
- Raise specific exceptions (`TableError`, `ValueError`, `FileNotFoundError`) with a message that names the input.
- Validate at boundaries (loading tables, CLI arguments, external responses); trust data inside.

## Testing
See the Testing section of `CLAUDE.md`. In short: tests mirror the source tree, shared fixtures live in
`tests/conftest.py`, every function has normal / edge / invalid-input cases, every decision-table rule has a
hand-written case in `EXPECTED`, seeds are fixed, long runs are marked `@pytest.mark.slow`.
