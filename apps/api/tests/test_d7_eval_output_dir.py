"""The deterministic regression gate must not write into the committed results.

``evals/results`` is a dated record of a real-embedding run. The gate runs both
evaluations with the fake provider, so it has to point them at a scratch directory.
Both entry points already take ``--output-dir``; these tests pin that the default is
still the committed directory (every direct invocation keeps working as before), that
an explicit directory is honoured, and that the Makefile recipe uses it and asserts
against the same location.

The pipelines themselves (database, API, model) are replaced with stubs: what is under
test is where the files land, not what they contain.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals import grounded_run, run

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMITTED_RESULTS = REPO_ROOT / "apps" / "api" / "evals" / "results"


class _NullClient:
    def __enter__(self) -> _NullClient:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _stub_retrieval_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_eval_settings", lambda provider: object())
    monkeypatch.setattr(run, "_prepare_database", lambda settings: None)
    monkeypatch.setattr(run, "load_documents", lambda: ())
    monkeypatch.setattr(run, "load_queries", lambda: ())
    monkeypatch.setattr(run, "create_app", lambda settings: object())
    monkeypatch.setattr(run, "TestClient", lambda app: _NullClient())
    monkeypatch.setattr(run, "_index_corpus", lambda client, documents: {})
    monkeypatch.setattr(run, "_run_queries", lambda client, queries: ([], {}))
    monkeypatch.setattr(run, "summarise", lambda mode, judged: mode)
    monkeypatch.setattr(run, "_results_payload", lambda *args: {"stub": True})
    monkeypatch.setattr(run, "_markdown_report", lambda *args: "report\n")
    monkeypatch.setattr(run, "_print_summary", lambda summaries, output_dir: None)


def _stub_grounded_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(grounded_run, "_eval_settings", lambda tier: object())
    monkeypatch.setattr(grounded_run, "_prepare_database", lambda settings: None)
    monkeypatch.setattr(grounded_run, "load_grounded_documents", lambda: ())
    monkeypatch.setattr(grounded_run, "load_grounded_cases", lambda: ())
    monkeypatch.setattr(grounded_run, "create_app", lambda settings: object())
    monkeypatch.setattr(grounded_run, "TestClient", lambda app: _NullClient())
    monkeypatch.setattr(grounded_run, "_index_corpus", lambda client, documents: None)
    monkeypatch.setattr(grounded_run, "_run_cases", lambda *args, **kwargs: [])
    monkeypatch.setattr(grounded_run, "_run_guardrails", lambda *args, **kwargs: [])
    monkeypatch.setattr(grounded_run, "_provider_facts", lambda client, tier: {})
    monkeypatch.setattr(grounded_run, "summarise", lambda outcomes: SimpleNamespace())
    monkeypatch.setattr(grounded_run, "_results_payload", lambda *args: {"stub": True})
    monkeypatch.setattr(grounded_run, "_markdown_report", lambda *args: "report\n")
    monkeypatch.setattr(grounded_run, "_print_summary", lambda *args: None)


def test_default_output_directories_are_the_committed_results() -> None:
    assert run.DEFAULT_OUTPUT_DIR == COMMITTED_RESULTS
    assert grounded_run.DEFAULT_OUTPUT_DIR == COMMITTED_RESULTS / "grounded"


def test_retrieval_run_defaults_to_the_committed_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_retrieval_run(monkeypatch)
    # Redirect the default so the test cannot overwrite the real record.
    monkeypatch.setattr(run, "DEFAULT_OUTPUT_DIR", tmp_path / "default")

    # ``main`` reads DEFAULT_OUTPUT_DIR when it builds the parser, so patching it is a
    # faithful stand-in for "no --output-dir given".
    assert run.main(["--provider", "fake"]) == 0
    assert (tmp_path / "default" / "results.json").is_file()
    assert (tmp_path / "default" / "REPORT.md").is_file()


def test_retrieval_run_honours_an_explicit_output_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_retrieval_run(monkeypatch)
    monkeypatch.setattr(run, "DEFAULT_OUTPUT_DIR", tmp_path / "default")
    explicit = tmp_path / "scratch" / "regression"

    assert run.main(["--provider", "fake", "--output-dir", str(explicit)]) == 0

    assert (explicit / "results.json").is_file()
    assert (explicit / "REPORT.md").is_file()
    assert not (tmp_path / "default").exists()


def test_grounded_run_defaults_to_the_committed_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_grounded_run(monkeypatch)
    monkeypatch.setattr(grounded_run, "DEFAULT_OUTPUT_DIR", tmp_path / "default")

    assert grounded_run.main(["--tier", "deterministic"]) == 0
    assert (tmp_path / "default" / "results-deterministic.json").is_file()
    assert (tmp_path / "default" / "REPORT-deterministic.md").is_file()


def test_grounded_run_honours_an_explicit_output_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_grounded_run(monkeypatch)
    monkeypatch.setattr(grounded_run, "DEFAULT_OUTPUT_DIR", tmp_path / "default")
    explicit = tmp_path / "scratch" / "regression" / "grounded"

    assert grounded_run.main(["--tier", "deterministic", "--output-dir", str(explicit)]) == 0

    assert (explicit / "results-deterministic.json").is_file()
    assert (explicit / "REPORT-deterministic.md").is_file()
    assert not (tmp_path / "default").exists()


def _gate_recipe() -> list[str]:
    lines = (REPO_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("verify-deterministic-regression:")
    )
    recipe: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line.startswith("\t"):
            break
        recipe.append(line)
    return recipe


def test_makefile_gate_never_targets_the_committed_results() -> None:
    recipe = "\n".join(line for line in _gate_recipe() if not line.lstrip("\t").startswith("@#"))

    assert "evals/results" not in recipe
    assert "--output-dir $(GATE_RESULTS_DIR)\n" in recipe + "\n"
    assert "--output-dir $(GATE_RESULTS_DIR)/grounded" in recipe


def test_makefile_gate_asserts_against_the_directory_it_wrote() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    gate_dir = re.search(r"^GATE_RESULTS_DIR := (\S+)$", makefile, re.MULTILINE)
    assert gate_dir, "GATE_RESULTS_DIR is not defined"
    directory = gate_dir.group(1)

    recipe = "\n".join(_gate_recipe())
    assert f'Path("{directory}/results.json")' in recipe
    assert f'Path("{directory}/grounded/results-deterministic.json")' in recipe


def test_gate_directory_is_git_ignored_and_inside_the_writable_mount() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    directory = re.search(r"^GATE_RESULTS_DIR := (\S+)$", makefile, re.MULTILINE).group(1)  # type: ignore[union-attr]

    # Compose mounts apps/api/evals (writable) at /app/evals.
    assert directory.startswith("evals/")
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "tmp/" in ignored
    assert "tmp" in Path(directory).parts
