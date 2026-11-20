"""``evals.grounded_replay`` replays captured drafts through the real validator and metrics.

Fixture run directories are built here from real ``GroundedAnswerDraft`` JSON with neutral
text. Their recorded verdicts come from calling the product's own ``validate_draft`` inside
the builder, so a fixture says what the product would have recorded, not what the replay tool
hopes to find. ``tests/d8_02_builders.py`` is not used: it writes placeholder raw text.
"""

from __future__ import annotations

import html
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from claimtrace_api.db.models import ClaimType
from claimtrace_api.grounding.context import repair_instruction
from claimtrace_api.grounding.draft import GroundedAnswerDraft
from claimtrace_api.grounding.evidence import (
    EvidenceCandidate,
    EvidenceCatalog,
    build_catalog,
    evidence_id_for_position,
)
from claimtrace_api.grounding.validation import GroundedOutputError, validate_draft
from claimtrace_api.services.grounded_generation import GroundedGenerationService
from evals import grounded_replay
from evals.grounded_capture import prompt_digest, sha256_text
from evals.grounded_dataset import load_grounded_cases, load_grounded_documents
from evals.grounded_metrics import CaseOutcome

API_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_RUN = API_ROOT / "evals" / "results" / "d8" / "2026-11-19-f4792fb-44522325577"
requires_committed_run = pytest.mark.skipif(
    not (COMMITTED_RUN / "grounded" / "r1" / "diagnostics-ollama.json").is_file(),
    reason="committed D8-02 Run A directory not present",
)

SYSTEM_TEXT = "Neutral system prompt for the fixture."
CASES = {case.id: case for case in load_grounded_cases()}
FILENAMES = {document.id: document.filename for document in load_grounded_documents()}
CORPUS_IDS = {filename: corpus_id for corpus_id, filename in FILENAMES.items()}

G01 = "g01-single-storage"
G02 = "g02-single-sampling-period"
G03 = "g03-single-coolant-material"
G04 = "g04-multi-storage-capacity"
G05 = "g05-multi-thermal-components"
G06 = "g06-multi-valve-conditions"
G07 = "g07-paraphrase-overwrite"
G11 = "g11-scoped-collector-no-valve"
G13 = "g13-unanswerable-applicant"


def draft(
    *statements: tuple[str, list[str]],
    flag: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "supported_statements": [{"text": text, "evidence_ids": ids} for text, ids in statements],
        "insufficient_evidence": flag,
        "insufficient_reason": reason,
    }


STRAY = "evidence_not_specific_enough"


@dataclass
class Spec:
    case_id: str
    catalog: list[tuple[str, int]]
    #: One draft per model call; ``None`` is a provider error.
    drafts: list[dict[str, Any] | None]
    question: str = "Neutral question."


def default_specs() -> list[Spec]:
    two_collector = [("collector", 1), ("collector", 4)]
    return [
        # accepted on attempt 0
        Spec(G01, two_collector, [draft(("Neutral statement one.", ["EV-001"]))]),
        # rejected (stray reason), then accepted
        Spec(
            G02,
            [("collector", 6), ("collector", 1)],
            [
                draft(("Neutral statement two.", ["EV-001"]), reason=STRAY),
                draft(("Neutral statement two.", ["EV-001"])),
            ],
        ),
        # rejected twice
        Spec(
            G03,
            [("thermal", 3), ("thermal", 1)],
            [
                draft(("Neutral statement three.", ["EV-001"]), reason=STRAY),
                draft(("Neutral statement three.", ["EV-001"]), reason=STRAY),
            ],
        ),
        # provider error
        Spec(G04, two_collector, [None]),
        # a bare decline (flag true, reason null), then a proper decline
        Spec(
            G05,
            [("thermal", 1), ("thermal", 6)],
            [draft(flag=True), draft(flag=True, reason=STRAY)],
        ),
        # stray reason and no statements: dropping the reason changes the violation
        Spec(
            G06,
            [("thermal", 2), ("thermal", 5)],
            [draft(reason=STRAY), draft(reason=STRAY)],
        ),
        # an id the model made up, then accepted
        Spec(
            G07,
            [("collector", 4), ("collector", 5)],
            [
                draft(("Neutral statement seven.", ["NOT-AN-ID-001"])),
                draft(("Neutral statement seven.", ["EV-001"])),
            ],
        ),
        # an out-of-scope claim cited: the label forbids thermal#1 here
        Spec(
            G11,
            [("thermal", 1), ("collector", 1)],
            [draft(("Neutral statement eleven.", ["EV-001"]))],
        ),
        # an unanswerable question answered
        Spec(G13, [("adversarial", 3)], [draft(("Neutral statement thirteen.", ["EV-001"]))]),
    ]


def _catalog(entries: list[tuple[str, int]]) -> EvidenceCatalog:
    candidates = tuple(
        EvidenceCandidate(
            document_id=uuid.uuid5(uuid.NAMESPACE_URL, document),
            document_name=document,
            claim_number=number,
            claim_type=ClaimType.INDEPENDENT,
            depends_on=(),
            text="",
            spans=(),
            fused_rank=position,
            fused_score=0.0,
        )
        for position, (document, number) in enumerate(entries, start=1)
    )
    return build_catalog(candidates, retrieved_candidate_count=len(candidates))


def _user_prompt(spec: Spec) -> str:
    blocks = [
        f'<evidence id="{evidence_id_for_position(position)}">\n'
        f"Document: {html.escape(FILENAMES[document])}\nClaim: {number}\n"
        "Text:\nNeutral claim text.\n</evidence>"
        for position, (document, number) in enumerate(spec.catalog, start=1)
    ]
    return "\n\n".join([f"<question>\n{html.escape(spec.question)}\n</question>", *blocks])


def build_case(spec: Spec, system: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Run the service's loop with the real validator; return result, raw case, system map."""
    catalog = _catalog(spec.catalog)
    user0 = _user_prompt(spec)
    prompt = user0
    attempts: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    final: Any = None
    for index, payload in enumerate(spec.drafts):
        raw = json.dumps(payload) if payload is not None else None
        call = {
            "attempt": index,
            "system_prompt_sha256": sha256_text(system),
            "user_prompt": prompt,
            "user_prompt_truncated": False,
            "raw_output": raw,
            "raw_output_truncated": False,
            "raw_output_sha256": sha256_text(raw) if raw is not None else None,
            "http": [],
        }
        record: dict[str, Any] = {
            "attempt": index,
            "outcome": "provider_error",
            "violation": None,
            "provider_error_code": "llm_timeout" if payload is None else None,
            "prompt_sha256": prompt_digest([("system", system), ("user", prompt)]),
            "raw_output_sha256": call["raw_output_sha256"],
            "done_reason": "stop",
            "prompt_eval_count": 800 + index,
            "eval_count": 100,
        }
        calls.append(call)
        attempts.append(record)
        if payload is None:
            final = ("provider", None)
            break
        parsed = GroundedAnswerDraft.model_validate(payload)
        try:
            final = ("ok", validate_draft(parsed, catalog=catalog, limits=grounded_replay.LIMITS))
            record["outcome"] = "accepted"
            break
        except GroundedOutputError as error:
            record["outcome"] = "rejected"
            record["violation"] = error.violation.value
            if index == len(spec.drafts) - 1:
                code = GroundedGenerationService._to_app_error(error, repaired=index > 0).code
                final = ("refused", code.value)
            else:
                prompt = (user0 + repair_instruction(catalog, problem=error.feedback)).strip()

    case = CASES[spec.case_id]
    kind, value = final
    if kind == "ok":
        outcome = CaseOutcome(
            case, 200, None, value.insufficient_evidence,
            value.insufficient_reason.value if value.insufficient_reason else None,
            len(value.statements), len(value.statements),
            frozenset((e.candidate.document_name, e.candidate.claim_number) for e in value.cited),
            True, 0, 0, 0, 0, 0.0,
        )  # fmt: skip
    else:
        code_value = value if kind == "refused" else "llm_timeout"
        outcome = CaseOutcome(
            case, 502, code_value, False, None, 0, 0, frozenset(), True, 0, 0, 0, 0, 0.0
        )
    result = {
        "id": spec.case_id,
        "status": outcome.status,
        "error_code": outcome.error_code,
        "insufficient_evidence": outcome.insufficient_evidence,
        "insufficient_reason": outcome.insufficient_reason,
        "statements": outcome.statement_count,
        "cited": sorted(f"{d}#{n}" for d, n in outcome.cited),
        "end_to_end_success": outcome.end_to_end_success,
        "diagnostics": {
            "schema_version": 1,
            "catalog": [
                {"evidence_id": evidence_id_for_position(i), "document": d, "claim_number": n}
                for i, (d, n) in enumerate(spec.catalog, start=1)
            ],
            "attempts": attempts,
        },
    }
    return result, {"id": spec.case_id, "calls": calls}, {sha256_text(system): system}


Tweak = Callable[[dict[str, Any], dict[str, Any]], None]


def write_segment(
    folder: Path,
    specs: list[Spec],
    *,
    repeat: int,
    system: str = SYSTEM_TEXT,
    tweak: Tweak | None = None,
    diagnostics: bool = True,
) -> None:
    folder.mkdir(parents=True)
    per_case, raw_cases, system_prompts = [], [], {}
    for spec in specs:
        result, raw_case, prompts = build_case(spec, system)
        if not diagnostics:
            del result["diagnostics"]
        per_case.append(result)
        raw_cases.append(raw_case)
        system_prompts.update(prompts)
    results = {"tier": "ollama", "per_case": per_case}
    raw = {
        "schema_version": 1,
        "tier": "ollama",
        "system_prompts": system_prompts,
        "format_schema_sha256": None,
        "cases": raw_cases,
    }
    if tweak is not None:
        tweak(results, raw)
    (folder / "results-ollama.json").write_text(json.dumps(results), encoding="utf-8")
    if diagnostics:
        (folder / "diagnostics-ollama.json").write_text(json.dumps(raw), encoding="utf-8")
    (folder / "segment.json").write_text(
        json.dumps({"ollama_image_tag": "0.40.16", "repeat_index": repeat}), encoding="utf-8"
    )


def build_run(
    tmp_path: Path,
    *,
    tweak: Tweak | None = None,
    diagnostics: bool = True,
    segments: int = 1,
    specs: list[Spec] | None = None,
) -> Path:
    run = tmp_path / "run"
    for repeat in range(1, segments + 1):
        chosen = specs if specs is not None else default_specs()
        write_segment(
            run / "grounded" / f"r{repeat}",
            chosen,
            repeat=repeat,
            tweak=tweak if repeat == 1 else None,
            diagnostics=diagnostics,
        )
    return run


def run_tool(capsys: pytest.CaptureFixture[str], *argv: str | Path) -> tuple[int, str, str]:
    code = grounded_replay.main([str(a) for a in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def prepared_by_case(tmp_path: Path) -> dict[str, grounded_replay.Prepared]:
    run = build_run(tmp_path)
    segment = grounded_replay.load_segment(
        "r1",
        "ollama",
        run / "grounded" / "r1",
        corpus_ids=CORPUS_IDS,
        cases=CASES,
    )
    assert segment is not None and segment.ok, segment and segment.failures
    return {p.case.id: p for p in segment.prepared}


def case_tweak(case_id: str, change: Callable[[dict[str, Any], dict[str, Any]], None]) -> Tweak:
    def apply(results: dict[str, Any], raw: dict[str, Any]) -> None:
        change(
            next(r for r in results["per_case"] if r["id"] == case_id),
            next(c for c in raw["cases"] if c["id"] == case_id),
        )

    return apply


# -- 1-2: the self-check -----------------------------------------------------------------------


def test_self_check_passes_on_a_consistent_fixture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run_tool(capsys, build_run(tmp_path))
    assert (code, err) == (0, "")
    assert "self-check: PASS (9 cases, 14 attempts;" in out
    assert "not replayable by record: provider_error=1" in out


@pytest.mark.parametrize(
    ("name", "change", "expected"),
    [
        (
            "recorded violation altered",
            lambda r, c: r["diagnostics"]["attempts"][0].update(violation="uncited_statement"),
            "verdict_mismatch_attempt_0",
        ),
        (
            "raw hash altered",
            lambda r, c: c["calls"][0].update(raw_output_sha256="0" * 64),
            "raw_hash_mismatch_attempt_0",
        ),
        (
            "truncation flag set",
            lambda r, c: c["calls"][0].update(raw_output_truncated=True),
            "truncated_attempt_0",
        ),
        (
            "catalog entry disagrees with the prompt",
            lambda r, c: r["diagnostics"]["catalog"][0].update(claim_number=7),
            "catalog_mismatch_prompt",
        ),
        (
            "attempt-1 prompt digest altered",
            lambda r, c: r["diagnostics"]["attempts"][1].update(prompt_sha256="a" * 64),
            "repair_prompt_differs",
        ),
        (
            "served outcome altered",
            lambda r, c: r.update(end_to_end_success=not r["end_to_end_success"]),
            "served_outcome_mismatch",
        ),
    ],
)
def test_self_check_refuses_the_segment_for_each_inconsistency(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    name: str,
    change: Callable[[dict[str, Any], dict[str, Any]], None],
    expected: str,
) -> None:
    case_id = G03 if "digest" in name or "violation" in name else G02
    run = build_run(tmp_path, tweak=case_tweak(case_id, change))
    code, out, _ = run_tool(capsys, run)
    assert code == 3, name
    assert "self-check: FAIL" in out
    assert f"{case_id}: " in out and expected in out
    assert "-- first_draft" not in out  # a refused segment prints no counterfactual table


# -- 3: the rules ------------------------------------------------------------------------------


def test_current_rule_matches_the_real_validator(tmp_path: Path) -> None:
    prepared = prepared_by_case(tmp_path)[G02]
    first = prepared.attempts[0].draft
    assert first is not None and prepared.catalog is not None
    with pytest.raises(GroundedOutputError) as raised:
        validate_draft(first, catalog=prepared.catalog, limits=grounded_replay.LIMITS)
    result = grounded_replay.run_flow(prepared, "first_draft", "current")
    assert result.verdicts == [raised.value.violation.value]
    assert result.outcome is not None and result.outcome.status == 502
    assert result.outcome.error_code == "grounded_output_invalid"


def test_drop_stray_reason_lets_a_false_plus_reason_draft_pass(tmp_path: Path) -> None:
    result = grounded_replay.run_flow(
        prepared_by_case(tmp_path)[G02], "first_draft", "drop_stray_reason"
    )
    assert result.verdicts == ["pass"]
    assert result.outcome is not None
    assert (result.outcome.status, result.outcome.insufficient_evidence) == (200, False)
    assert result.outcome.insufficient_reason is None
    assert result.outcome.cited == frozenset({("collector", 6)})


def test_honour_stray_reason_serves_it_as_a_decline_with_its_reason(tmp_path: Path) -> None:
    result = grounded_replay.run_flow(
        prepared_by_case(tmp_path)[G02], "first_draft", "honour_stray_reason"
    )
    assert result.outcome is not None
    assert (result.outcome.status, result.outcome.insufficient_evidence) == (200, True)
    assert result.outcome.insufficient_reason == STRAY


@pytest.mark.parametrize("rule", ["drop_stray_reason", "honour_stray_reason"])
def test_neither_counterfactual_touches_a_bare_decline(tmp_path: Path, rule: str) -> None:
    result = grounded_replay.run_flow(prepared_by_case(tmp_path)[G05], "first_draft", rule)
    assert result.verdicts == ["contradictory_insufficiency"]
    assert result.outcome is not None and result.outcome.status == 502


# -- 4: the four two_attempt branches ----------------------------------------------------------


def test_two_attempt_is_served_at_attempt_zero_without_the_repair(tmp_path: Path) -> None:
    result = grounded_replay.run_flow(
        prepared_by_case(tmp_path)[G02], "two_attempt", "drop_stray_reason"
    )
    assert result.verdicts == ["pass"]  # the recorded repair call would not have happened
    assert result.not_replayable is None


def test_two_attempt_uses_the_repair_when_its_prompt_matches(tmp_path: Path) -> None:
    prepared = prepared_by_case(tmp_path)
    served = grounded_replay.run_flow(prepared[G02], "two_attempt", "current")
    assert served.verdicts == ["contradictory_insufficiency", "pass"]
    assert served.outcome is not None and served.outcome.status == 200
    failed = grounded_replay.run_flow(prepared[G03], "two_attempt", "current")
    assert failed.verdicts == ["contradictory_insufficiency"] * 2
    assert failed.outcome is not None
    assert failed.outcome.error_code == "grounded_repair_failed"


def test_two_attempt_without_a_recorded_repair_is_not_replayable(tmp_path: Path) -> None:
    prepared = prepared_by_case(tmp_path)[G03]
    del prepared.attempts[1]
    result = grounded_replay.run_flow(prepared, "two_attempt", "current")
    assert result.not_replayable == "repair_not_recorded"
    assert result.outcome is None


def test_two_attempt_with_different_feedback_is_not_replayable(tmp_path: Path) -> None:
    # Dropping the reason turns this draft's violation into "no supported statements", so the
    # feedback the model would have been sent differs from the recorded one.
    prepared = prepared_by_case(tmp_path)[G06]
    first = grounded_replay.run_flow(prepared, "first_draft", "drop_stray_reason")
    assert first.verdicts == ["no_supported_statements"]
    result = grounded_replay.run_flow(prepared, "two_attempt", "drop_stray_reason")
    assert result.not_replayable == "repair_prompt_differs"
    assert result.verdicts == ["no_supported_statements"]


def test_provider_error_is_not_replayable_and_not_a_self_check_failure(tmp_path: Path) -> None:
    prepared = prepared_by_case(tmp_path)[G04]
    for flow in grounded_replay.FLOWS:
        assert (
            grounded_replay.run_flow(prepared, flow, "current").not_replayable == "provider_error"
        )


# -- 5: scoring goes through CaseOutcome and the real labels --------------------------------------


def test_scoring_uses_the_real_case_labels(tmp_path: Path) -> None:
    prepared = prepared_by_case(tmp_path)

    answerable = grounded_replay.run_flow(prepared[G01], "first_draft", "current").outcome
    assert CASES[G01].answerable and CASES[G01].relevant == {("collector", 1)}
    assert answerable is not None and answerable.end_to_end_success

    answered_unanswerable = grounded_replay.run_flow(
        prepared[G13], "first_draft", "current"
    ).outcome
    assert not CASES[G13].answerable
    assert answered_unanswerable is not None
    assert answered_unanswerable.status == 200
    assert not answered_unanswerable.answerability_correct
    assert not answered_unanswerable.end_to_end_success

    leaked = grounded_replay.run_flow(prepared[G11], "first_draft", "current").outcome
    assert ("thermal", 1) in CASES[G11].forbidden
    assert leaked is not None and leaked.cited_forbidden == {("thermal", 1)}
    assert not leaked.end_to_end_success


def test_distinct_statement_count_uses_stripped_text(tmp_path: Path) -> None:
    spec = Spec(
        G01,
        [("collector", 1)],
        [draft(("Same.", ["EV-001"]), ("  Same.  ", ["EV-001"]), ("Other.", ["EV-001"]))],
    )
    run = build_run(tmp_path, specs=[spec])
    segment = grounded_replay.load_segment(
        "r1", "ollama", run / "grounded" / "r1", corpus_ids=CORPUS_IDS, cases=CASES
    )
    assert segment is not None
    result = grounded_replay.run_flow(segment.prepared[0], "first_draft", "current")
    assert result.outcome is not None
    assert (result.outcome.statement_count, result.distinct_statement_count) == (3, 2)


# -- 6: nothing the model or the prompt wrote reaches the output -----------------------------


def test_sentinel_text_never_reaches_stdout_or_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    marker = "SENTINEL-7c1f9e"
    specs = default_specs()
    specs[0].drafts = [draft((f"Statement {marker}-statement.", ["EV-001"]))]
    specs[0].question = f"Question {marker}-prompt."
    specs[6].drafts[0] = draft(("Neutral statement seven.", [f"{marker}-id"]))
    run = tmp_path / "run"
    write_segment(run / "grounded" / "r1", specs, repeat=1, system=f"System {marker}-system.")
    out_file = tmp_path / "out" / "replay.json"
    out_file.parent.mkdir()
    code, out, err = run_tool(capsys, run, "--json-out", out_file)
    assert code == 0, err
    assert marker not in out and marker not in err
    assert marker not in out_file.read_text(encoding="utf-8")
    document = json.loads(out_file.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    # The invented id is counted, never echoed.
    assert document["segments"][0]["observables"]["evidence_ids_not_in_catalog_all_attempts"] == 1


# -- 7: paths and missing files -----------------------------------------------------------------


def test_json_out_inside_the_run_directory_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = build_run(tmp_path)
    target = run / "grounded" / "replay.json"
    code, out, err = run_tool(capsys, run, "--json-out", target)
    assert code == 2 and out == ""
    assert "--json-out must not be inside RUN_DIR" in err
    assert not target.exists()


def test_a_missing_required_file_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = build_run(tmp_path)
    (run / "grounded" / "r1" / "diagnostics-ollama.json").unlink()
    code, _, err = run_tool(capsys, run)
    assert code == 2 and "REFUSED" in err
    code, _, err = run_tool(capsys, tmp_path / "nowhere")
    assert code == 2


def test_a_directory_without_diagnostics_exits_0_with_the_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run_tool(capsys, build_run(tmp_path, diagnostics=False))
    assert code == 0
    assert out.strip() == "no diagnostics captured; nothing to replay"


def test_rules_option_selects_a_subset(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _ = run_tool(capsys, build_run(tmp_path), "--rules", "drop_stray_reason")
    assert "-- first_draft / drop_stray_reason" in out
    assert "honour_stray_reason" not in out and "-- first_draft / current" not in out


def test_segment_pairs_count_prompt_and_raw_differences(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = tmp_path / "run"
    first = default_specs()
    second = default_specs()
    second[0].question = "A different neutral question."  # unequal prompts for one case
    second[1].drafts[0] = draft(
        ("Different neutral words.", ["EV-001"]), reason=STRAY
    )  # equal prompt, new raw
    write_segment(run / "grounded" / "r1", first, repeat=1)
    write_segment(run / "grounded" / "r2", second, repeat=2)
    code, out, _ = run_tool(capsys, run, "--rules", "current")
    assert code == 0
    assert (
        f"repeat_pair r1-r2: cases_compared=9 prompt_differs=1 ({G01}) "
        "equal_prompt_raw_differences=1 equal_prompt_token_differences=0"
    ) in out


def test_stray_and_bare_first_drafts_are_counted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run_tool(capsys, build_run(tmp_path), "--rules", "current")
    # G02, G03, G06 start with a stray reason; G05 starts with a bare decline.
    assert "stray_reason_first_drafts=3, bare_decline_first_drafts=1" in out


# -- 8: the committed Run A directory -------------------------------------------------------------


@requires_committed_run
def test_committed_run_a_reproduces_its_record_and_the_counterfactuals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_file = tmp_path / "replay.json"
    code, _, err = run_tool(capsys, COMMITTED_RUN, "--json-out", out_file)
    assert (code, err) == (0, "")
    document = json.loads(out_file.read_text(encoding="utf-8"))
    segments = {s["name"]: s for s in document["segments"]}
    assert set(segments) == {"oracle", "r1", "r2"}
    assert all(s["self_check"]["ok"] for s in segments.values())
    for name in ("r1", "r2"):
        tables = segments[name]["tables"]
        assert segments[name]["observables"]["stray_reason_first_drafts"] == 16
        current = tables["two_attempt/current"]["aggregate"]
        assert current["end_to_end_success_rate"] == 0.125
        drop = tables["first_draft/drop_stray_reason"]["aggregate"]
        assert (drop["end_to_end_success_rate"], drop["insufficient_recall"]) == (0.6875, 0.0)
        honour = tables["first_draft/honour_stray_reason"]["aggregate"]
        assert (honour["end_to_end_success_rate"], honour["insufficient_recall"]) == (0.1875, 1.0)
    pair = document["pairs"][0]
    assert pair["segments"] == ["r1", "r2"]
    assert pair["prompt_differs"] == 1
    assert pair["prompt_differs_cases"] == ["g10-dependency-method-chain"]
    assert pair["equal_prompt_raw_differences"] == 0
