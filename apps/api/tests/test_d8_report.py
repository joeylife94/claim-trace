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
import random
import re
import shutil
import string
from pathlib import Path
from typing import Any

import pytest

from evals import d8_report
from tests import d8_02_builders as builders

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
    assert summary["non_claims"] == d8_report.non_claims(MODEL)
    assert len(d8_report.NON_CLAIMS) == 6
    for sentence in d8_report.non_claims(MODEL):
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


def test_refuses_oracle_file_with_a_dropped_guardrail(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mutate(run / "grounded" / "results-deterministic.json", lambda p: p["guardrails"].pop())
    assert_refused(run, capsys, "guardrail names")


def test_refuses_oracle_file_with_a_renamed_guardrail(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def rename(payload: dict[str, Any]) -> None:
        payload["guardrails"][0]["name"] = "renamed-payload"

    mutate(run / "grounded" / "results-deterministic.json", rename)
    assert_refused(run, capsys, "guardrail names")


def test_m2_heading_does_not_call_oracle_answers_scripted(run: Path) -> None:
    assert run_tool(run) == 0
    report = (run / "D8-REPORT.md").read_text(encoding="utf-8")
    heading = next(line for line in report.splitlines() if line.startswith("## M2"))
    assert "oracle in place of a language model" in heading
    assert "scripted" not in heading


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


# -- D8-02: compatibility with the committed run directories --------------------


COMMITTED_RUN = COMMITTED / "d8" / "2026-11-16-aa492be"
requires_committed_run = pytest.mark.skipif(
    not (COMMITTED_RUN / "ENVIRONMENT.json").is_file(), reason="committed D8-01 run not present"
)


def _copy_tree(source: Path, target: Path) -> Path:
    shutil.copytree(source, target)
    for stale in ("D8-SUMMARY.json", "D8-REPORT.md"):
        (target / stale).unlink(missing_ok=True)
    return target


def _normalised(report: str) -> list[str]:
    """A report without the two lines that legitimately change (timestamp, model sentence)."""
    return [
        line
        for line in report.splitlines()
        if not line.startswith(("Report generated at", "- One embedding model and one"))
    ]


@requires_committed_run
def test_committed_d8_01_run_still_validates_and_renders_as_before(tmp_path: Path) -> None:
    run = _copy_tree(COMMITTED_RUN, tmp_path / "committed")
    assert run_tool(run) == 0
    report = (run / "D8-REPORT.md").read_text(encoding="utf-8")
    committed = (COMMITTED_RUN / "D8-REPORT.md").read_text(encoding="utf-8")
    assert _normalised(report) == _normalised(committed)
    for heading in (
        "## Machine",
        "## Why M3 cases failed",
        "## Rejections by rule",
        "## Tokens and context",
        "## Within-machine contrasts",
        "## Ollama runtime",
    ):
        assert heading not in report
    summary = _read_json(run / "D8-SUMMARY.json")
    assert "diagnostics" not in summary
    assert "stability_by_tag" not in summary
    committed_summary = _read_json(COMMITTED_RUN / "D8-SUMMARY.json")
    for key in committed_summary:
        if key not in ("generated_at", "non_claims"):
            assert summary[key] == committed_summary[key], key


def test_a_run_of_another_model_names_that_model_in_the_second_non_claim(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    for number in (1, 2):
        mutate(
            run / "grounded" / f"r{number}" / "results-ollama.json",
            lambda p: p["provider"].update(model="qwen2.5:3b"),
        )
    env = dict(ENVIRONMENT, ollama_model="qwen2.5:3b")
    _write_json(run / "ENVIRONMENT.json", env)
    assert (
        d8_report.main(
            ["--run-dir", str(run), "--expected-llm-model", "qwen2.5:3b", "--expected-repeats", "2"]
        )
        == 0
    )
    report = (run / "D8-REPORT.md").read_text(encoding="utf-8")
    assert "one local LLM (`qwen2.5:3b`), on a CPU runner" in report
    assert "1.5B" not in report
    assert report.index("one local LLM") < report.index("## Environment")


def test_second_non_claim_without_an_llm_tier_names_no_model(tmp_path: Path) -> None:
    run = make_run(tmp_path, repeats=0)
    assert run_tool(run, repeats=0) == 0
    report = (run / "D8-REPORT.md").read_text(encoding="utf-8")
    assert "the LLM tier was not run" in report.split("## How to read")[0]


def test_violation_constant_equals_the_product_enum() -> None:
    from claimtrace_api.grounding.validation import GroundedViolation

    assert tuple(v.value for v in GroundedViolation) == d8_report.GROUNDED_VIOLATIONS


# -- D8-02: a run with segments and diagnostics ---------------------------------


TAGS = ["0.40.16", "0.17.1", "0.40.16", "0.17.1"]


def _contrast_run(tmp_path: Path, *, version_differs: int, repeat_differs: int = 0) -> Path:
    """Four segments A,B,A,B. The first ``version_differs`` cases differ between tags and the
    first ``repeat_differs`` differ between the two repeats of a tag (second repeat only)."""
    case_ids = [c["id"] for c in _read_json(builders.REAL_OLLAMA)["per_case"]]

    def raw_variant(tag: str | None, index: int, case_id: str) -> str:
        position = case_ids.index(case_id)
        token = "t" if tag == "0.40.16" else "u"
        if position >= version_differs:
            token = "t"
        if index == 2 and position < repeat_differs:
            token += "-second"
        return token

    return builders.build_run(tmp_path, tags=TAGS, raw_variant=raw_variant)


def run_segments(run: Path, segments: int = 4) -> int:
    return run_tool(run, repeats=segments)


def test_a_run_with_segments_validates_and_renders_every_new_section(tmp_path: Path) -> None:
    run = _contrast_run(tmp_path, version_differs=6, repeat_differs=1)
    assert run_segments(run) == 0
    report = (run / "D8-REPORT.md").read_text(encoding="utf-8")
    summary = _read_json(run / "D8-SUMMARY.json")
    for heading in (
        "## Machine",
        "## Ollama runtime",
        "## Why M3 cases failed",
        "## Rejections by rule",
        "## Tokens and context",
        "## Same evidence in both tiers",
        "## Within-machine contrasts",
    ):
        assert heading in report, heading
    assert (
        "Raw prompts and model output are in diagnostics-<tier>.json; they are untrusted text "
        "and are not reproduced in this report."
    ) in report
    # Machine: sanitised name, 12 hex of the fingerprint, selected flags, kernel, image.
    assert "Intel(R) Xeon(R) Platinum 8370C CPU @ 2.80GHz" in report
    assert "fedcba987654" in report and "fedcba9876540" not in report
    assert "avx512_vnni" in report and "6.8.0-1017-azure" in report and "20261110.1.0" in report
    # Columns carry the tag.
    assert "r1 (0.40.16)" in report and "r2 (0.17.1)" in report
    # Stability is per tag when there are two tags.
    assert "Tag `0.40.16`:" in report and "Tag `0.17.1`:" in report

    diag = summary["diagnostics"]
    assert [s["ollama_image_tag"] for s in diag["segments"]] == TAGS
    assert [s["repeat_index"] for s in diag["segments"]] == [1, 1, 2, 2]
    assert diag["machine"]["cpu_fingerprint"].startswith("fedcba987654")
    base = _read_json(builders.REAL_OLLAMA)["per_case"]
    failed = [c for c in base if c["status"] != 200]
    first = diag["m3"][0]
    assert len(first["failed_cases"]) == len(failed)
    assert first["repaired_200_cases"] == 0
    # Each failed case had two rejected attempts: one count per attempt, per rule.
    assert sum(first["rejections_by_rule"]["attempt_0"].values()) == len(failed)
    assert sum(first["rejections_by_rule"]["attempt_1"].values()) == len(failed)
    assert set(first["rejections_by_rule"]["attempt_0"]) <= set(d8_report.GROUNDED_VIOLATIONS)
    assert first["tokens"]["context_length_in_use"] == 4096
    assert first["tokens"]["max_prompt_plus_output"] == 1140  # 800 + 200 repair prompt + 140
    assert first["tokens"]["attempts_done_reason_length"] == 0
    assert diag["same_evidence"]["r1"]["differing_cases"] == []
    assert summary["stability_by_tag"].keys() == {"0.40.16", "0.17.1"}


def test_contrast_counts_and_the_fixed_rule_when_a_version_effect_is_shown(
    tmp_path: Path,
) -> None:
    # Repeats of one tag differ in 1 case; the two tags differ in 6: 6 >= 1 + 4 for every pair.
    run = _contrast_run(tmp_path, version_differs=6, repeat_differs=1)
    assert run_segments(run) == 0
    contrasts = _read_json(run / "D8-SUMMARY.json")["diagnostics"]["contrasts"]
    pairs = {tuple(p["segments"]): p for p in contrasts["pairs"]}
    assert len(pairs) == 6
    key = "different_first_attempt_raw_output_hash"
    assert pairs[(1, 3)]["kind"] == pairs[(2, 4)]["kind"] == "repeat pair"
    assert pairs[(1, 2)]["kind"] == "version pair"
    assert pairs[(1, 3)][key] == 1 and pairs[(2, 4)][key] == 1
    assert pairs[(1, 2)][key] == 6
    assert contrasts["largest_repeat_pair_count"] == 1
    assert contrasts["version_effect"] == "shown"
    report = (run / "D8-REPORT.md").read_text(encoding="utf-8")
    assert "Version effect on this machine: **shown**" in report


def test_version_effect_is_not_shown_when_the_margin_is_three(tmp_path: Path) -> None:
    run = _contrast_run(tmp_path, version_differs=4, repeat_differs=1)  # 4 < 1 + 4
    assert run_segments(run) == 0
    contrasts = _read_json(run / "D8-SUMMARY.json")["diagnostics"]["contrasts"]
    assert contrasts["version_effect"] == "not_shown"
    report = (run / "D8-REPORT.md").read_text(encoding="utf-8")
    assert "Version effect on this machine: **not shown**" in report
    assert "largest repeat-pair count 1, smallest version-pair count" in report


def test_one_tag_has_repeat_pairs_only_and_no_version_verdict(tmp_path: Path) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16", "0.40.16"])
    assert run_segments(run, 2) == 0
    contrasts = _read_json(run / "D8-SUMMARY.json")["diagnostics"]["contrasts"]
    assert [p["kind"] for p in contrasts["pairs"]] == ["repeat pair"]
    assert contrasts["version_effect"] is None
    assert "not assessed" in (run / "D8-REPORT.md").read_text(encoding="utf-8")


def test_two_tags_without_a_repeat_pair_do_not_claim_an_effect(tmp_path: Path) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16", "0.17.1"])
    assert run_segments(run, 2) == 0
    contrasts = _read_json(run / "D8-SUMMARY.json")["diagnostics"]["contrasts"]
    assert contrasts["version_effect"] == "not_shown"
    assert "no repeat pair" in contrasts["reason"]


def test_prompt_hash_difference_against_the_oracle_tier_is_listed(tmp_path: Path) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16"], legacy_repeats=1)
    target = run / "grounded" / "r1" / "results-ollama.json"

    def change(payload: dict[str, Any]) -> None:
        payload["per_case"][2]["diagnostics"]["attempts"][0]["prompt_sha256"] = "f" * 64

    mutate(target, change)
    assert run_segments(run, 1) == 0
    same = _read_json(run / "D8-SUMMARY.json")["diagnostics"]["same_evidence"]["r1"]
    assert same["differing_cases"] == [_read_json(target)["per_case"][2]["id"]]
    assert same["differing_cases"][0] in (run / "D8-REPORT.md").read_text(encoding="utf-8")


def test_tokens_at_the_context_and_length_stops_are_counted(tmp_path: Path) -> None:
    run = builders.build_run(
        tmp_path, tags=["0.40.16"], done_reason="length", prompt_tokens=3900, context_length=4096
    )
    assert run_segments(run, 1) == 0
    tokens = _read_json(run / "D8-SUMMARY.json")["diagnostics"]["m3"][0]["tokens"]
    assert tokens["attempts_done_reason_length"] > 0
    assert tokens["attempts_at_or_over_context"] > 0
    assert tokens["max_prompt"] == 4100


def test_a_missing_context_length_is_reported_as_not_recorded(tmp_path: Path) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16"], context_length=None)
    assert run_segments(run, 1) == 0
    assert "not recorded" in (run / "D8-REPORT.md").read_text(encoding="utf-8")


# -- D8-02: malformed new facts are refused -------------------------------------


def _mutate_case_diag(run: Path, change: Any) -> None:
    mutate(
        run / "grounded" / "r1" / "results-ollama.json",
        lambda payload: change(payload["per_case"][0]["diagnostics"]),
    )


@pytest.mark.parametrize(
    ("change", "needle"),
    [
        (lambda d: d["attempts"].extend([d["attempts"][0]] * 2), "at most 2 entries"),
        (lambda d: d["attempts"][0].update(outcome="exploded"), "outcome is outside"),
        (lambda d: d["attempts"][0].update(violation="made_up_rule"), "violation is outside"),
        (lambda d: d["attempts"][0].update(eval_count=-1), "eval_count"),
        (lambda d: d["attempts"][0].update(prompt_eval_count="12"), "prompt_eval_count"),
        (lambda d: d["attempts"][0].update(raw_output_sha256="xyz"), "raw_output_sha256"),
        (lambda d: d["attempts"][0].update(wall_seconds=-0.5), "wall_seconds"),
        (lambda d: d.update(schema_version=2), "schema_version"),
    ],
)
def test_refuses_malformed_diagnostics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: Any, needle: str
) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16"], legacy_repeats=1)
    _mutate_case_diag(run, change)
    assert run_tool(run, repeats=1) == 1
    assert needle in capsys.readouterr().err
    assert not (run / "D8-SUMMARY.json").exists()


def test_refuses_diagnostics_present_for_only_some_cases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16"], legacy_repeats=1)
    mutate(
        run / "grounded" / "r1" / "results-ollama.json",
        lambda payload: payload["per_case"][3].pop("diagnostics"),
    )
    assert run_tool(run, repeats=1) == 1
    assert "only some of the cases" in capsys.readouterr().err


def test_refuses_when_the_environment_says_diagnostics_were_captured_but_a_tier_has_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16"], legacy_repeats=1)

    def strip(payload: dict[str, Any]) -> None:
        for case in payload["per_case"]:
            case.pop("diagnostics")

    mutate(run / "grounded" / "results-deterministic.json", strip)
    assert run_tool(run, repeats=1) == 1
    assert "oracle tier has none" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("change", "needle"),
    [
        (lambda m: m.update(ollama_image_tag="bad tag!"), "ollama_image_tag is missing"),
        (lambda m: m.update(segment=7), "segment is 7"),
        (lambda m: m.update(repeat_index=3), "repeat_index is 3"),
        (lambda m: m.update(schema_version=9), "schema_version"),
    ],
)
def test_refuses_a_malformed_segment_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: Any, needle: str
) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16", "0.40.16"])
    mutate(run / "grounded" / "r2" / "segment.json", change)
    assert run_tool(run, repeats=2) == 1
    assert needle in capsys.readouterr().err


def test_refuses_segment_files_present_for_only_some_segments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16", "0.40.16"])
    (run / "grounded" / "r2" / "segment.json").unlink()
    assert run_tool(run, repeats=2) == 1
    assert "only some of the segments" in capsys.readouterr().err


def test_refuses_runtimes_that_disagree_with_the_segments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16", "0.17.1"])
    mutate(run / "ENVIRONMENT.json", lambda e: e["ollama_runtimes"].pop())
    assert run_tool(run, repeats=2) == 1
    assert "ollama_runtimes tags" in capsys.readouterr().err


def test_a_malformed_runtime_file_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16"], legacy_repeats=1)
    mutate(run / "grounded" / "r1" / "ollama-runtime.json", lambda r: r.update(ps="nope"))
    assert run_tool(run, repeats=1) == 1
    assert "ps is not a list" in capsys.readouterr().err


# -- D8-02: nothing a model or a server wrote reaches the report -----------------


def test_sentinel_text_never_reaches_the_report_or_the_summary(tmp_path: Path) -> None:
    token = "SENTINEL-" + "".join(random.choices(string.ascii_lowercase, k=12))
    hostile = f"{token} <script>alert(1)</script> | pipe | `tick` [x](http://e)"
    run = builders.build_run(
        tmp_path, tags=["0.40.16", "0.17.1"], raw_files=hostile, done_reason="bogus " + hostile
    )

    # A bogus CPU model name, a bogus kernel and a bogus done_reason / error code.
    def hostile_env(env: dict[str, Any]) -> None:
        env["runner"]["cpu"]["model_name"] = hostile
        env["runner"]["cpu"]["vendor_id"] = hostile
        env["runner"]["kernel"] = hostile
        env["runner"]["image_version"] = hostile
        env["ollama_runtimes"][0]["version"] = hostile

    mutate(run / "ENVIRONMENT.json", hostile_env)
    for number in (1, 2):
        mutate(
            run / "grounded" / f"r{number}" / "segment.json",
            lambda m: m.update(ollama_version=hostile, ollama_image_digest=hostile),
        )
        mutate(
            run / "grounded" / f"r{number}" / "ollama-runtime.json",
            lambda r: r.update(api_version=hostile),
        )
        mutate(
            run / "grounded" / f"r{number}" / "results-ollama.json",
            lambda p: next(c for c in p["per_case"] if c["status"] != 200)["diagnostics"][
                "attempts"
            ][0].update(provider_error_code=hostile),
        )
        # Raw model text and prompt text sit in the case diagnostics too.
        mutate(
            run / "grounded" / f"r{number}" / "results-ollama.json",
            lambda p: p["per_case"][0]["diagnostics"].update(error_detail=hostile),
        )
    assert run_segments(run, 2) == 0
    report = (run / "D8-REPORT.md").read_text(encoding="utf-8")
    summary_text = (run / "D8-SUMMARY.json").read_text(encoding="utf-8")
    for text in (report, summary_text):
        assert token not in text
        assert "<script>" not in text
    assert "other" in report
    # A bogus done_reason renders as `other` in the failure table.
    failure_table = report.split("## Why M3 cases failed")[1].split("## Rejections")[0]
    assert "| other / other |" in failure_table


def test_the_report_tool_never_opens_the_raw_text_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16"], legacy_repeats=1, raw_files="RAW")
    opened: list[str] = []
    original = Path.read_text

    def spy(self: Path, *args: Any, **kwargs: Any) -> str:
        opened.append(self.name)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    assert run_segments(run, 1) == 0
    assert opened
    assert not [name for name in opened if name.startswith("diagnostics-")]
    assert "ollama-server.log" not in opened


def test_emit_carries_the_new_files_of_a_segment_run(tmp_path: Path) -> None:
    run = builders.build_run(tmp_path, tags=["0.40.16"], legacy_repeats=1, raw_files="RAW")
    assert run_segments(run, 1) == 0
    buffer = io.BytesIO()
    paths = [path for path, _, _ in d8_report.emit(run, buffer)]
    assert "grounded/r1/segment.json" in paths
    assert "grounded/r1/ollama-runtime.json" in paths


# -- D8-02: the fixed version-effect rule is pinned at its edges ------------------


def _contrast_of(run: Path) -> dict[str, Any]:
    assert run_segments(run) == 0
    contrasts: dict[str, Any] = _read_json(run / "D8-SUMMARY.json")["diagnostics"]["contrasts"]
    return contrasts


def test_a_version_pair_exactly_at_the_margin_shows_the_effect(tmp_path: Path) -> None:
    # Repeat pairs differ in 1 case, every version pair in exactly 5 = 1 + 4.
    contrasts = _contrast_of(_contrast_run(tmp_path, version_differs=5, repeat_differs=1))
    key = "different_first_attempt_raw_output_hash"
    assert {p[key] for p in contrasts["pairs"] if p["kind"] == "version pair"} == {5}
    assert contrasts["largest_repeat_pair_count"] == 1
    assert contrasts["version_effect"] == "shown"


def test_every_version_pair_must_meet_the_margin(tmp_path: Path) -> None:
    case_ids = [c["id"] for c in _read_json(builders.REAL_OLLAMA)["per_case"]]

    def raw_variant(tag: str | None, index: int, case_id: str) -> str:
        position = case_ids.index(case_id)
        if tag == "0.40.16":
            return "t"
        # The second repeat of the other tag matches the first tag in more cases.
        return "u" if position < (6 if index == 1 else 4) else "t"

    run = builders.build_run(tmp_path, tags=TAGS, raw_variant=raw_variant)
    contrasts = _contrast_of(run)
    key = "different_first_attempt_raw_output_hash"
    version = sorted(p[key] for p in contrasts["pairs"] if p["kind"] == "version pair")
    assert version == [4, 4, 6, 6]
    assert contrasts["largest_repeat_pair_count"] == 2
    # Some version pairs meet the margin (6 >= 2 + 4) and some do not (4 < 6).
    assert contrasts["version_effect"] == "not_shown"


def test_a_missing_raw_output_hash_withholds_the_verdict(tmp_path: Path) -> None:
    run = _contrast_run(tmp_path, version_differs=8, repeat_differs=0)

    def drop(payload: dict[str, Any]) -> None:
        payload["per_case"][0]["diagnostics"]["attempts"][0]["raw_output_sha256"] = None

    mutate(run / "grounded" / "r3" / "results-ollama.json", drop)
    contrasts = _contrast_of(run)
    assert contrasts["version_effect"] == "not_shown"
    assert "missing" in contrasts["reason"]
    assert "Reason: first-attempt raw-output hashes are missing" in (
        run / "D8-REPORT.md"
    ).read_text(encoding="utf-8")
