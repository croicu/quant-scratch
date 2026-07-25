# quant-scratch

A collection of short, self-contained experiments — each backed by its own CLI tool — for validating or invalidating assumptions about signals and correlations across financial market parameters. Findings and strategies are presented in [quant-research](https://github.com/croicu/quant-research).

---

## Install

```bash
pip install -e ".[dev]"
```

## Lint

```bash
ruff check src/ tests/
ruff format src/ tests/
```

## Test

```bash
pytest
pytest tests/unit/test_foo.py::test_bar   # single test
```
