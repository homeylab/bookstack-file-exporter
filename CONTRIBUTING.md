# Contributing

## Running Tests

This project uses [uv](https://docs.astral.sh/uv/) and [Taskfile](https://taskfile.dev) for development — the `task` targets below wrap the underlying `uv run` commands (`task --list` shows them all). Sync dev dependencies, then run the suite:

```bash
task sync
task test
```

The pytest run includes coverage by default (configured in `pyproject.toml`). For an HTML coverage report:

```bash
task test:cov
open htmlcov/index.html
```

Run only unit tests (skip integration):

```bash
task test:unit
```

Run only integration tests:

```bash
task test:integration
```

Lint the package and tests:

```bash
task lint
```
