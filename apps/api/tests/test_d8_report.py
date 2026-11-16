"""The D8 report tool decides whether a measurement can be trusted at all.

Its happy path is the least interesting part: what matters is that a run built from
a fake provider, a wrong model, a missing repeat or a truncated file is refused, with
a reason on stderr and no summary on disk. Each fail-closed rule therefore has its own
test, built by mutating a copy of the committed real-provider files (the 2026-07-26
record), which are the fixtures here and are only ever read.

Paths are resolved from the api folder, never from a repository root: in CI these
tests run inside the api image, where ``/app/tests`` and ``/app/evals`` have no
repository above them.
"""

from __future__ import annotations

import copy
import io
import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from evals import d8_report

API_ROOT = Path(__file__).resolve().parents[1]
COMMITTED = API_ROOT / "evals" / "results"
REAL_RETRIEVAL = COMMITTED / "results.json"
REAL_ORACLE = COMMITTED / "grounded" / "results-deterministic.json"
REAL_OLLAMA = COMMITTED / "grounded" / "results-ollama.json"
MODEL = "qwen2.5:1.5b"

ENVIRONMENT: dict[str, Any] = {
    "git_sha": "0123456789abcdef0123456789abcdef01234567",
    "run_id": "9999",
    "run_attempt": "1",
    "event_name": "pull_request",
    "runner": {"nproc": 4, "mem_total_mb": 15990, "os": "Ubuntu 24.04.1 LTS"},
    "api_image_id": "sha256:aaaa",
    "ollama_image_digest": "ollama/ollama@sha256:bbbb",
    "ollama_version": "0.5.0",
    "ollama_model": MODEL,
    "ollama_model_id": "sha256:cccc",
    "embedding_model": "intfloat/multilingual-e5-small",
    "embedding_model_revision": "deadbeef",
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def make_run(root: Path, *, repeats: int = 2) -> Path:
    """A valid run directory made of copies of the committed real-provider files."""
    run = root / "run"
    (run / "retrieval").mkdir(parents=True)
    shutil.copy(REAL_RETRIEVAL, run / "retrieval" / "results.json")
    (run / "grounded").mkdir()
    shutil.copy(REAL_ORACLE, run / "grounded" / "results-deterministic.json")
    for number in range(1, repeats + 1):
        (run / "grounded" / f"r{number}").mkdir()
        shutil.copy(REAL_OLLAMA, run / "grounded" / f"r{number}" / "results-ollama.json")
    _write_json(run / "ENVIRONMENT.json", ENVIRONMENT)
    return run


def mutate(path: Path, change: Any) -> None:
    payload = _read_json(path)
    change(payload)
    _write_json(path, payload)


def run_tool(run: Path, *extra: str, repeats: int = 2) -> int:
    return d8_report.main(
        [
            "--run-dir",
            str(run),
            "--expected-llm-model",
            MODEL,
            "--expected-repeats",
            str(repeats),
            *extra,
        ]
    )


def assert_refused(
    run: Path, capsys: pytest.CaptureFixture[str], needle: str, *, repeats: int = 2
) -> str:
    assert run_tool(run, repeats=repeats) == 1
    stderr = capsys.readouterr().err
    assert needle in stderr, stderr
    assert "no summary was written" in stderr
    assert not (run / "D8-SUMMARY.json").exists()
    assert not (run / "D8-REPORT.md").exists()
    return stderr


@pytest.fixture
def run(tmp_path: Path) -> Path:
    return make_run(tmp_path)


# -- the committed fixtures really are real-provider files -------------------


def test_fixtures_are_real_provider_files() -> None:
    assert _read_json(REAL_RETRIEVAL)["profile"]["embedding_provider"] == "sentence-transformers"
    assert _read_json(REAL_ORACLE)["provider"]["provider"] == "oracle"
    assert _read_json(REAL_OLLAMA)["provider"]["model"] == MODEL


def test_expected_counts_come_from_the_committed_datasets() -> None:
    counts = d8_report._expected_counts()
    assert counts["retrieval"] == {"documents": 2, "claims": 26, "queries": 19}
    assert {k: counts["grounded"][k] for k in ("documents", "claims", "cases")} == {
        "documents": 3,
        "claims": 23,
        "cases": 16,
    }
    assert len(counts["grounded"]["case_ids"]) == 16


# -- positive ------------------------------------------------------------------


def test_valid_run_writes_summary_and_report(run: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_tool(run) == 0
    summary = _read_json(run / "D8-SUMMARY.json")
    report = (run / "D8-REPORT.md").read_text(encoding="utf-8")

    assert summary["schema_version"] == 1
    assert summary["git_sha"] == ENVIRONMENT["git_sha"]
    assert summary["run_id"] == "9999"
    assert summary["environment"]["runner"]["nproc"] == 4
    assert summary["warnings"] == []
    # Every non-claim is verbatim, in the summary and in the report, and first.
    assert summary["non_claims"] == list(d8_report.NON_CLAIMS)
    assert len(d8_report.NON_CLAIMS) == 6
    for sentence in d8_report.NON_CLAIMS:
        assert f"- {sentence}\n" in report
    assert report.index("## Non-claims") < report.index("## Environment")
    assert "Real public documents and description retrieval were not measured." in report


def test_summary_carries_the_values_of_the_inputs(run: Path) -> None:
    assert run_tool(run) == 0
    summary = _read_json(run / "D8-SUMMARY.json")
    retrieval = _read_json(REAL_RETRIEVAL)
    oracle = _read_json(REAL_ORACLE)
    ollama = _read_json(REAL_OLLAMA)

    for mode in ("dense", "lexical", "hybrid"):
        assert summary["retrieval"]["modes"][mode] == retrieval["metrics"][mode]
        assert (
            summary["baseline_2026_07_26"]["retrieval"]["modes"][mode] == retrieval["metrics"][mode]
        )
    assert summary["grounded_oracle"]["metrics"] == oracle["metrics"]
    assert summary["grounded_oracle"]["guardrails"]["total"] == len(oracle["guardrails"])
    assert summary["grounded_oracle"]["guardrails"]["refused"] == sum(
        1 for g in oracle["guardrails"] if g["refused"]
    )

    # g01 and g16 are what the fixture file says, for the oracle and each repeat.
    def case(payload: dict[str, Any], prefix: str) -> dict[str, Any]:
        return next(c for c in payload["per_case"] if c["id"].startswith(prefix))

    oracle_g01 = summary["grounded_oracle"]["g01"]
    assert oracle_g01["end_to_end_success"] is case(oracle, "g01-")["end_to_end_success"]
    assert oracle_g01["cited"] == case(oracle, "g01-")["cited"]
    assert oracle_g01["forbidden_cited"] == case(oracle, "g01-")["forbidden_cited"]

    assert [r["repeat"] for r in summary["grounded_llm"]] == [1, 2]
    for repeat in summary["grounded_llm"]:
        assert repeat["metrics"] == ollama["metrics"]
        assert repeat["g01"]["cited"] == case(ollama, "g01-")["cited"]
        assert repeat["g16"]["id"] == case(ollama, "g16-")["id"]
        assert repeat["g16"]["end_to_end_success"] is case(ollama, "g16-")["end_to_end_success"]
        failed = [
            (c["id"], c["status"], c["error_code"])
            for c in ollama["per_case"]
            if c["status"] != 200 or c["error_code"]
        ]
        assert [(f["id"], f["status"], f["error_code"]) for f in repeat["failed_cases"]] == failed
    assert failed, "the committed file has a recorded 502, which must be listed, not refused"


def test_identical_repeats_are_fully_stable(run: Path) -> None:
    assert run_tool(run) == 0
    stability = _read_json(run / "D8-SUMMARY.json")["stability"]
    assert stability["computed"] is True
    assert stability["case_count"] == 16
    assert stability["identical_end_to_end_outcome"] == 16
    assert stability["differing_cases"] == []


def test_differing_repeats_are_listed(run: Path) -> None:
    def flip(payload: dict[str, Any]) -> None:
        payload["per_case"][1]["end_to_end_success"] = not payload["per_case"][1][
            "end_to_end_success"
        ]
        payload["per_case"][5]["end_to_end_success"] = not payload["per_case"][5][
            "end_to_end_success"
        ]

    mutate(run / "grounded" / "r2" / "results-ollama.json", flip)
    assert run_tool(run) == 0
    stability = _read_json(run / "D8-SUMMARY.json")["stability"]
    assert stability["identical_end_to_end_outcome"] == 14
    assert [d["id"] for d in stability["differing_cases"]] == [
        "g02-single-sampling-period",
        "g06-multi-valve-conditions",
    ]
    assert stability["differing_cases"][0]["end_to_end_success_per_repeat"] == [True, False]


def test_single_repeat_does_not_claim_stability(tmp_path: Path) -> None:
    run = make_run(tmp_path, repeats=1)
    assert run_tool(run, repeats=1) == 0
    stability = _read_json(run / "D8-SUMMARY.json")["stability"]
    assert stability["computed"] is False
    assert "Not computed" in (run / "D8-REPORT.md").read_text(encoding="utf-8")


def test_llm_tier_skipped_with_zero_repeats(tmp_path: Path) -> None:
    run = make_run(tmp_path, repeats=0)
    environment = dict(ENVIRONMENT)
    for key in ("ollama_image_digest", "ollama_version", "ollama_model", "ollama_model_id"):
        environment[key] = None
    _write_json(run / "ENVIRONMENT.json", environment)
    assert run_tool(run, repeats=0) == 0
    summary = _read_json(run / "D8-SUMMARY.json")
    assert summary["grounded_llm"] == []
    assert "not run" in (run / "D8-REPORT.md").read_text(encoding="utf-8")


def test_missing_embedding_revision_is_a_warning_not_a_refusal(run: Path) -> None:
    environment = dict(ENVIRONMENT, embedding_model_revision=None)
    _write_json(run / "ENVIRONMENT.json", environment)
    assert run_tool(run) == 0
    summary = _read_json(run / "D8-SUMMARY.json")
    assert len(summary["warnings"]) == 1
    assert "embedding_model_revision" in summary["warnings"][0]
    assert "## Warnings" in (run / "D8-REPORT.md").read_text(encoding="utf-8")


def test_report_puts_baseline_beside_the_run_and_states_no_cause(run: Path) -> None:
    assert run_tool(run) == 0
    report = (run / "D8-REPORT.md").read_text(encoding="utf-8")
    assert "2026-07-26" in report
    assert "| 0.7696 |" in report  # a value exactly as the input wrote it
    assert "No cause is attributed to any of them" in report
    # Everything after the (verbatim) non-claims must not attribute differences.
    body = report[report.index("## How to read this report") :]
    for word in (
        "because",
        "caused",
        "due to",
        "thanks to",
        "improv",
        "regress",
        "degrad",
        "result of",
    ):
        assert word not in body.lower(), word


def test_report_is_independent_of_the_working_directory(
    run: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert run_tool(run) == 0


# -- fail-closed: retrieval ----------------------------------------------------


def test_refuses_fake_embedding_provider_in_retrieval(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(
        run / "retrieval" / "results.json", lambda p: p["profile"].update(embedding_provider="fake")
    )
    assert_refused(run, capsys, "embedding_provider is 'fake'")


def test_refuses_wrong_embedding_model_in_retrieval(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(
        run / "retrieval" / "results.json",
        lambda p: p["profile"].update(embedding_model="intfloat/multilingual-e5-base"),
    )
    assert_refused(run, capsys, "embedding_model is 'intfloat/multilingual-e5-base'")


@pytest.mark.parametrize(("key", "value"), [("documents", 3), ("claims", 25), ("queries", 18)])
def test_refuses_retrieval_counts(
    run: Path, capsys: pytest.CaptureFixture[str], key: str, value: int
) -> None:
    mutate(run / "retrieval" / "results.json", lambda p: p["corpus"].update({key: value}))
    assert_refused(run, capsys, f"corpus.{key} is {value}")


def test_refuses_retrieval_with_a_missing_mode(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(run / "retrieval" / "results.json", lambda p: p["metrics"].pop("hybrid"))
    assert_refused(run, capsys, "metrics for mode 'hybrid' are missing")


def test_refuses_retrieval_with_truncated_rows(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(run / "retrieval" / "results.json", lambda p: p.update(per_query=p["per_query"][:30]))
    assert_refused(run, capsys, "per_query has 30 rows, expected 57")


def test_refuses_truncated_json(run: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = run / "retrieval" / "results.json"
    path.write_text(path.read_text(encoding="utf-8")[:500], encoding="utf-8")
    assert_refused(run, capsys, "retrieval/results.json: unreadable or truncated JSON")


def test_refuses_missing_input_file(run: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (run / "grounded" / "results-deterministic.json").unlink()
    assert_refused(run, capsys, "grounded/results-deterministic.json: file is missing")


# -- fail-closed: oracle tier --------------------------------------------------


def test_refuses_oracle_file_with_another_provider(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(
        run / "grounded" / "results-deterministic.json",
        lambda p: p["provider"].update(provider="fake"),
    )
    assert_refused(run, capsys, "provider is 'fake', expected 'oracle'")


def test_refuses_oracle_file_over_fake_embeddings(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(
        run / "grounded" / "results-deterministic.json",
        lambda p: p["corpus"]["retrieval_profile"].update(embedding_provider="fake"),
    )
    assert_refused(run, capsys, "embedding_provider is 'fake'")


def test_refuses_oracle_file_with_wrong_embedding_model(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(
        run / "grounded" / "results-deterministic.json",
        lambda p: p["corpus"]["retrieval_profile"].update(embedding_model="other"),
    )
    assert_refused(run, capsys, "embedding_model is 'other'")


def test_refuses_oracle_file_without_guardrail_outcomes(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(run / "grounded" / "results-deterministic.json", lambda p: p.update(guardrails=[]))
    assert_refused(run, capsys, "recorded no guardrail outcomes")


def test_refuses_the_wrong_tier_in_a_file(run: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mutate(run / "grounded" / "results-deterministic.json", lambda p: p.update(tier="ollama"))
    assert_refused(run, capsys, "tier is 'ollama', expected 'deterministic'")


# -- fail-closed: LLM tier -----------------------------------------------------


def test_refuses_llm_file_with_fake_provider(run: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mutate(
        run / "grounded" / "r1" / "results-ollama.json",
        lambda p: p["provider"].update(provider="fake"),
    )
    assert_refused(run, capsys, "grounded/r1/results-ollama.json: provider is 'fake'")


def test_refuses_llm_file_with_the_oracle_as_provider(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copy(REAL_ORACLE, run / "grounded" / "r2" / "results-ollama.json")
    stderr = assert_refused(run, capsys, "grounded/r2/results-ollama.json: provider is 'oracle'")
    assert "tier is 'deterministic', expected 'ollama'" in stderr


def test_refuses_llm_file_with_another_model(run: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mutate(
        run / "grounded" / "r2" / "results-ollama.json",
        lambda p: p["provider"].update(model="qwen2.5:3b"),
    )
    assert_refused(run, capsys, "model is 'qwen2.5:3b', expected 'qwen2.5:1.5b'")


@pytest.mark.parametrize("flag", ["available", "model_available"])
def test_refuses_llm_file_reporting_unavailable(
    run: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    mutate(
        run / "grounded" / "r1" / "results-ollama.json",
        lambda p: p["provider"].update({flag: False}),
    )
    assert_refused(run, capsys, f"provider {flag} is False")


@pytest.mark.parametrize("flag", ["available", "model_available"])
def test_refuses_oracle_file_reporting_unavailable(
    run: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    mutate(
        run / "grounded" / "results-deterministic.json",
        lambda p: p["provider"].update({flag: False}),
    )
    assert_refused(run, capsys, f"provider {flag} is False")


def test_refuses_llm_file_over_fake_embeddings(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(
        run / "grounded" / "r1" / "results-ollama.json",
        lambda p: p["corpus"]["retrieval_profile"].update(embedding_provider="fake"),
    )
    assert_refused(run, capsys, "r1/results-ollama.json: embedding_provider is 'fake'")


@pytest.mark.parametrize(("key", "value"), [("documents", 2), ("claims", 22), ("cases", 15)])
def test_refuses_grounded_counts(
    run: Path, capsys: pytest.CaptureFixture[str], key: str, value: int
) -> None:
    mutate(
        run / "grounded" / "r1" / "results-ollama.json", lambda p: p["corpus"].update({key: value})
    )
    assert_refused(run, capsys, f"corpus.{key} is {value}")


def test_refuses_llm_file_with_missing_cases(run: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def cut(payload: dict[str, Any]) -> None:
        payload["per_case"] = payload["per_case"][:10]
        payload["metrics"]["case_count"] = 10

    mutate(run / "grounded" / "r2" / "results-ollama.json", cut)
    stderr = assert_refused(run, capsys, "metrics.case_count is 10, expected 16")
    assert "per_case ids differ from the committed cases" in stderr


def test_refuses_llm_file_with_guardrail_outcomes(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    guardrails = _read_json(REAL_ORACLE)["guardrails"]
    mutate(
        run / "grounded" / "r1" / "results-ollama.json", lambda p: p.update(guardrails=guardrails)
    )
    assert_refused(run, capsys, "must not carry guardrail outcomes")


def test_refuses_a_missing_repeat(run: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert_refused(run, capsys, "grounded/r3: repeat is missing", repeats=3)


def test_refuses_a_repeat_directory_without_its_file(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (run / "grounded" / "r2" / "results-ollama.json").unlink()
    assert_refused(run, capsys, "grounded/r2/results-ollama.json: file is missing")


def test_refuses_an_unexpected_repeat(run: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert_refused(run, capsys, "grounded/r2: repeat was not expected", repeats=1)


def test_refuses_repeats_present_when_none_are_expected(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert_refused(run, capsys, "grounded/r1: repeat was not expected", repeats=0)


# -- fail-closed: ENVIRONMENT.json ---------------------------------------------


@pytest.mark.parametrize("key", d8_report.ENVIRONMENT_REQUIRED_KEYS)
def test_refuses_a_missing_environment_field(
    run: Path, capsys: pytest.CaptureFixture[str], key: str
) -> None:
    mutate(run / "ENVIRONMENT.json", lambda p: p.pop(key))
    assert_refused(run, capsys, f"ENVIRONMENT.json: field '{key}' is missing")


@pytest.mark.parametrize("key", ["nproc", "mem_total_mb", "os"])
def test_refuses_a_missing_runner_field(
    run: Path, capsys: pytest.CaptureFixture[str], key: str
) -> None:
    mutate(run / "ENVIRONMENT.json", lambda p: p["runner"].pop(key))
    assert_refused(run, capsys, f"ENVIRONMENT.json: runner.{key} is missing")


@pytest.mark.parametrize("key", ["git_sha", "run_id", "api_image_id"])
def test_refuses_an_empty_environment_field(
    run: Path, capsys: pytest.CaptureFixture[str], key: str
) -> None:
    mutate(run / "ENVIRONMENT.json", lambda p: p.update({key: None}))
    assert_refused(run, capsys, f"ENVIRONMENT.json: field '{key}' is empty")


@pytest.mark.parametrize("key", d8_report.ENVIRONMENT_OLLAMA_KEYS)
def test_refuses_null_ollama_facts_when_repeats_are_expected(
    run: Path, capsys: pytest.CaptureFixture[str], key: str
) -> None:
    mutate(run / "ENVIRONMENT.json", lambda p: p.update({key: None}))
    assert_refused(run, capsys, f"ENVIRONMENT.json: field '{key}' is empty")


def test_refuses_environment_with_another_embedding_model(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(run / "ENVIRONMENT.json", lambda p: p.update(embedding_model="other"))
    assert_refused(run, capsys, "ENVIRONMENT.json: embedding_model is 'other'")


def test_refuses_environment_naming_another_ollama_model(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(run / "ENVIRONMENT.json", lambda p: p.update(ollama_model="qwen2.5:3b"))
    assert_refused(run, capsys, "ENVIRONMENT.json: ollama_model is 'qwen2.5:3b'")


def test_refuses_a_missing_environment_file(run: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (run / "ENVIRONMENT.json").unlink()
    assert_refused(run, capsys, "ENVIRONMENT.json: file is missing")


# -- fail-closed: baseline and general -----------------------------------------


def test_refuses_when_the_baseline_is_missing(
    run: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "no-baseline"
    empty.mkdir()
    assert run_tool(run, "--baseline-dir", str(empty)) == 1
    assert "baseline" in capsys.readouterr().err
    assert not (run / "D8-SUMMARY.json").exists()


def test_refuses_a_baseline_from_another_date(
    run: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = tmp_path / "baseline"
    shutil.copytree(COMMITTED, baseline)
    mutate(baseline / "results.json", lambda p: p.update(generated_at="2026-11-16T00:00:00+00:00"))
    assert run_tool(run, "--baseline-dir", str(baseline)) == 1
    assert "is not from 2026-07-26" in capsys.readouterr().err
    assert not (run / "D8-SUMMARY.json").exists()


def test_refuses_a_missing_run_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_tool(tmp_path / "nope") == 1
    assert "does not exist" in capsys.readouterr().err


def test_a_fake_run_is_refused_with_one_line_per_violation(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What the local fake-provider evaluations produce: every file says 'fake'."""
    mutate(
        run / "retrieval" / "results.json", lambda p: p["profile"].update(embedding_provider="fake")
    )
    for number in (1, 2):
        mutate(
            run / "grounded" / f"r{number}" / "results-ollama.json",
            lambda p: (
                p["provider"].update(provider="fake"),
                p["corpus"]["retrieval_profile"].update(embedding_provider="fake"),
            ),
        )
    mutate(
        run / "grounded" / "results-deterministic.json",
        lambda p: p["corpus"]["retrieval_profile"].update(embedding_provider="fake"),
    )
    assert run_tool(run) == 1
    lines = [line for line in capsys.readouterr().err.splitlines() if line.startswith("D8 REFUSED")]
    assert len([line for line in lines if "'fake'" in line]) == 6
    assert not (run / "D8-SUMMARY.json").exists()


def test_a_refused_run_does_not_overwrite_an_earlier_summary_with_a_new_one(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The tool never writes on refusal; it also never emits."""
    mutate(
        run / "retrieval" / "results.json", lambda p: p["profile"].update(embedding_provider="fake")
    )
    assert run_tool(run, "--emit") == 1
    assert "D8-FILE-BEGIN" not in capsys.readouterr().out


# -- emit ----------------------------------------------------------------------


def test_emit_format_and_index(tmp_path: Path) -> None:
    root = tmp_path / "emit"
    (root / "sub").mkdir(parents=True)
    (root / "b.txt").write_bytes(b"no trailing newline")
    (root / "sub" / "a.txt").write_bytes("with newline, 한글\n".encode())
    (root / "empty.txt").write_bytes(b"")
    out = io.BytesIO()
    index = d8_report.emit(root, out)

    assert [entry[0] for entry in index] == ["b.txt", "empty.txt", "sub/a.txt"]
    text = out.getvalue().decode("utf-8")
    import hashlib

    digest = hashlib.sha256(b"no trailing newline").hexdigest()
    assert text.startswith(
        f"D8-FILE-BEGIN b.txt {digest} 19\nno trailing newline\nD8-FILE-END b.txt\n"
    )
    # The END marker is on its own line even without a trailing newline in the file,
    # and a file that does end with one gets a blank line before its END marker.
    assert "with newline, 한글\n\nD8-FILE-END sub/a.txt\n" in text
    index_lines = text.splitlines()[-3:]
    assert index_lines == [f"D8-INDEX {path} {sha} {size}" for path, sha, size in index]


def test_main_emit_prints_every_file_including_the_summary(
    run: Path, capfdbinary: pytest.CaptureFixture[bytes]
) -> None:
    assert run_tool(run, "--emit") == 0
    out = capfdbinary.readouterr().out.decode("utf-8")
    paths = re.findall(r"^D8-FILE-BEGIN (\S+) ", out, flags=re.MULTILINE)
    assert paths == sorted(paths)
    assert {
        "D8-SUMMARY.json",
        "D8-REPORT.md",
        "ENVIRONMENT.json",
        "retrieval/results.json",
        "grounded/results-deterministic.json",
        "grounded/r1/results-ollama.json",
        "grounded/r2/results-ollama.json",
    } == set(paths)
    assert len(re.findall(r"^D8-INDEX ", out, flags=re.MULTILINE)) == len(paths)
    assert out.rstrip("\n").splitlines()[-1].startswith("D8-INDEX ")


def test_emit_refuses_files_a_log_cannot_carry(tmp_path: Path) -> None:
    binary = tmp_path / "bin"
    binary.mkdir()
    (binary / "x.bin").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(d8_report.EmitRefused, match="not UTF-8"):
        d8_report.emit(binary, io.BytesIO())

    crlf = tmp_path / "crlf"
    crlf.mkdir()
    (crlf / "x.txt").write_bytes(b"a\r\nb\n")
    with pytest.raises(d8_report.EmitRefused, match="carriage return"):
        d8_report.emit(crlf, io.BytesIO())

    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / "real.txt").write_text("x", encoding="utf-8")
    (linked / "link.txt").symlink_to(linked / "real.txt")
    with pytest.raises(d8_report.EmitRefused, match="symbolic links"):
        d8_report.emit(linked, io.BytesIO())


def test_validation_failure_content_is_a_copy_not_a_view() -> None:
    """Guards the fixtures: mutating a deep copy never touches the committed files."""
    payload = copy.deepcopy(_read_json(REAL_RETRIEVAL))
    payload["profile"]["embedding_provider"] = "fake"
    assert _read_json(REAL_RETRIEVAL)["profile"]["embedding_provider"] == "sentence-transformers"
