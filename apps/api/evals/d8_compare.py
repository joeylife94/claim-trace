"""Compare two D8 run directories case by case, from facts only.

    python -m evals.d8_compare RUN_A RUN_B

Prints plain text and exits 0; exits 2 with a message on stderr when a directory is
missing or lacks a required file (``ENVIRONMENT.json``, ``grounded/results-deterministic.json``).

What it compares:

* oracle tier (M2): per case, whether the evidence catalog and the first-attempt prompt
  hash are equal, and both catalogs when they differ (``EV-001=collector#4 ...``);
* LLM tier (M3): for every Ollama image tag present on both sides, segments with the same
  ``repeat_index`` are paired; per case the status and end-to-end outcome on each side,
  whether the first-attempt raw-output hash is equal, and the violation of each attempt.

It reads only ``ENVIRONMENT.json``, ``results-*.json`` and ``segment.json``. It never opens
``diagnostics-*.json`` or a server log, and every string it prints is a number, a hash
prefix, a closed-set code or matches a strict pattern (else ``other``), so model text cannot
reach the output. A directory from before D8-02 (no ``segment.json``, no diagnostics) is
accepted: what is available is printed and what is missing is said. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evals.d8_report import (
    CODE_PATTERN,
    CPU_NAME_PATTERN,
    GROUNDED_VIOLATIONS,
    SHORT_FACT_PATTERN,
    TAG_PATTERN,
)

_REPEAT_DIR = re.compile(r"^r(\d+)$")
_ID_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_EVIDENCE_ID_PATTERN = re.compile(r"EV-[0-9]{1,6}")
_SHA_PATTERN = re.compile(r"[0-9a-f]{7,64}")
_HEX64 = re.compile(r"[0-9a-f]{64}")


class CompareRefused(Exception):
    """A directory cannot be read as a D8 run (exit status 2)."""


@dataclass
class Seg:
    number: int
    payload: dict[str, Any]
    tag: str | None
    repeat_index: int
    version: str | None


@dataclass
class Run:
    env: dict[str, Any]
    oracle: dict[str, Any]
    segments: list[Seg] = field(default_factory=list)


def _clean(value: Any, pattern: re.Pattern[str]) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) and pattern.fullmatch(value) else "other"


def _load(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise CompareRefused(f"{label}: required file is missing")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CompareRefused(f"{label}: unreadable JSON ({error.__class__.__name__})") from error
    if not isinstance(loaded, dict):
        raise CompareRefused(f"{label}: top level is not a JSON object")
    return loaded


def _load_grounded(path: Path, label: str) -> dict[str, Any]:
    payload = _load(path, label)
    if not isinstance(payload.get("per_case"), list):
        raise CompareRefused(f"{label}: no per_case list")
    return payload


def load_run(directory: Path, side: str) -> Run:
    if not directory.is_dir():
        raise CompareRefused(f"{side}: not a directory")
    env = _load(directory / "ENVIRONMENT.json", f"{side}: ENVIRONMENT.json")
    oracle = _load_grounded(
        directory / "grounded" / "results-deterministic.json",
        f"{side}: grounded/results-deterministic.json",
    )
    run = Run(env=env, oracle=oracle)
    grounded = directory / "grounded"
    numbers = sorted(
        int(match.group(1))
        for child in grounded.iterdir()
        if child.is_dir() and (match := _REPEAT_DIR.match(child.name))
    )
    for number in numbers:
        folder = grounded / f"r{number}"
        label = f"{side}: grounded/r{number}"
        payload = _load_grounded(folder / "results-ollama.json", f"{label}/results-ollama.json")
        tag = version = None
        repeat_index = number
        if (folder / "segment.json").is_file():
            meta = _load(folder / "segment.json", f"{label}/segment.json")
            raw_tag = meta.get("ollama_image_tag")
            tag = raw_tag if isinstance(raw_tag, str) and TAG_PATTERN.fullmatch(raw_tag) else None
            index = meta.get("repeat_index")
            if isinstance(index, int) and not isinstance(index, bool) and index > 0:
                repeat_index = index
            version = _clean(meta.get("ollama_version"), SHORT_FACT_PATTERN)
        run.segments.append(Seg(number, payload, tag, repeat_index, version))
    return run


# -- reading a case's facts --------------------------------------------------


def _diag(case: dict[str, Any]) -> dict[str, Any] | None:
    diag = case.get("diagnostics")
    return diag if isinstance(diag, dict) else None


def _attempts(case: dict[str, Any]) -> list[dict[str, Any]]:
    diag = _diag(case)
    attempts = diag.get("attempts") if diag else None
    return [a for a in attempts if isinstance(a, dict)] if isinstance(attempts, list) else []


def _first(case: dict[str, Any], key: str) -> Any:
    attempts = _attempts(case)
    return attempts[0].get(key) if attempts else None


def _cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in payload["per_case"] if isinstance(c, dict)]


def _has_diagnostics(payload: dict[str, Any]) -> bool:
    return any(_diag(c) is not None for c in _cases(payload))


def _case_id(case: dict[str, Any]) -> str:
    return _clean(case.get("id"), _ID_PATTERN) or "other"


def _catalog(case: dict[str, Any]) -> list[tuple[Any, Any, Any]] | None:
    diag = _diag(case)
    catalog = diag.get("catalog") if diag else None
    if not isinstance(catalog, list):
        return None
    return [
        (e.get("evidence_id"), e.get("document"), e.get("claim_number"))
        for e in catalog
        if isinstance(e, dict)
    ]


def _format_catalog(catalog: list[tuple[Any, Any, Any]]) -> str:
    parts = []
    for evidence_id, document, number in catalog:
        shown_number = number if isinstance(number, int) and not isinstance(number, bool) else "?"
        parts.append(
            f"{_clean(evidence_id, _EVIDENCE_ID_PATTERN)}="
            f"{_clean(document, _ID_PATTERN)}#{shown_number}"
        )
    return " ".join(parts) if parts else "-"


def _attempt_label(attempt: dict[str, Any]) -> str:
    violation = attempt.get("violation")
    if violation in GROUNDED_VIOLATIONS:
        return str(violation)
    return _clean(attempt.get("outcome"), CODE_PATTERN) or "other"


def _violations(case: dict[str, Any]) -> str:
    attempts = _attempts(case)
    if not attempts:
        return "n/a"
    return ">".join(_attempt_label(a) for a in attempts)


def _outcome(case: dict[str, Any]) -> str:
    status = case.get("status")
    shown = status if isinstance(status, int) and not isinstance(status, bool) else "?"
    return f"{shown}/{'ok' if case.get('end_to_end_success') is True else 'fail'}"


def _equal(a: Any, b: Any) -> str:
    if a is None or b is None:
        return "n/a"
    return "equal" if a == b else "DIFFERENT"


def _hash(value: Any) -> str | None:
    return value if isinstance(value, str) and _HEX64.fullmatch(value) else None


# -- output ------------------------------------------------------------------


def _header(side: str, run: Run) -> list[str]:
    env = run.env
    runner = env.get("runner") if isinstance(env.get("runner"), dict) else {}
    cpu = runner.get("cpu") if isinstance(runner.get("cpu"), dict) else {}
    fingerprint = cpu.get("cpu_fingerprint")
    fingerprint_text = (
        fingerprint[:12] if isinstance(fingerprint, str) and _HEX64.fullmatch(fingerprint) else None
    )
    tags: dict[str, str | None] = {}
    for seg in run.segments:
        if seg.tag is not None:
            tags.setdefault(seg.tag, seg.version)
    if not tags:
        runtimes = env.get("ollama_runtimes")
        for item in runtimes if isinstance(runtimes, list) else []:
            if isinstance(item, dict) and isinstance(item.get("tag"), str):
                tag = _clean(item["tag"], TAG_PATTERN)
                if tag:
                    tags.setdefault(tag, _clean(item.get("version"), SHORT_FACT_PATTERN))
    tag_text = (
        ", ".join(f"{tag} (version {version or 'not recorded'})" for tag, version in tags.items())
        or "not recorded"
    )
    llm_diag = any(_has_diagnostics(s.payload) for s in run.segments)
    return [
        f"[{side}] git_sha: {_clean(env.get('git_sha'), _SHA_PATTERN) or 'not recorded'}",
        f"[{side}] run_id: {_clean(env.get('run_id'), SHORT_FACT_PATTERN) or 'not recorded'}",
        f"[{side}] cpu_fingerprint: {fingerprint_text or 'not recorded'}",
        f"[{side}] cpu_model: {_clean(cpu.get('model_name'), CPU_NAME_PATTERN) or 'not recorded'}",
        f"[{side}] ollama tags: {tag_text}",
        f"[{side}] llm segments: {len(run.segments) or 'none (LLM tier not run)'}",
        f"[{side}] diagnostics: oracle {'yes' if _has_diagnostics(run.oracle) else 'no'}, "
        f"llm {'yes' if llm_diag else 'no'}",
    ]


def _oracle_section(a: Run, b: Run) -> list[str]:
    lines = ["", "== Oracle tier (M2): evidence catalog and first-attempt prompt hash"]
    for side, run in (("A", a), ("B", b)):
        if not _has_diagnostics(run.oracle):
            lines.append(f"[{side}] has no diagnostics; catalog and prompt hash cannot be compared")
    cases_b = {_case_id(c): c for c in _cases(b.oracle)}
    differing_catalog = differing_prompt = compared = 0
    detail: list[str] = []
    for case_a in _cases(a.oracle):
        case_id = _case_id(case_a)
        case_b = cases_b.get(case_id)
        if case_b is None:
            lines.append(f"{case_id}  only in A")
            continue
        catalog_a, catalog_b = _catalog(case_a), _catalog(case_b)
        catalog = _equal(catalog_a, catalog_b)
        prompt = _equal(
            _hash(_first(case_a, "prompt_sha256")), _hash(_first(case_b, "prompt_sha256"))
        )
        compared += 1
        differing_catalog += catalog == "DIFFERENT"
        differing_prompt += prompt == "DIFFERENT"
        lines.append(
            f"{case_id}  catalog={catalog}  prompt_hash={prompt}  "
            f"status A={case_a.get('status')} B={case_b.get('status')}"
        )
        if catalog_a is not None and catalog_b is not None and catalog == "DIFFERENT":
            detail.append(f"  {case_id} catalog A: {_format_catalog(catalog_a)}")
            detail.append(f"  {case_id} catalog B: {_format_catalog(catalog_b)}")
    lines += detail
    lines.append(
        f"oracle summary: {compared} cases compared; catalog differs in {differing_catalog}; "
        f"first-attempt prompt hash differs in {differing_prompt}"
    )
    return lines


def _pair_lines(seg_a: Seg, seg_b: Seg, tag_name: str, totals: dict[str, int]) -> list[str]:
    both = _has_diagnostics(seg_a.payload) and _has_diagnostics(seg_b.payload)
    lines = [
        f"-- tag {tag_name}, repeat {seg_a.repeat_index}: A r{seg_a.number} vs B r{seg_b.number}"
        + ("" if both else " (diagnostics missing on at least one side; hashes and violations n/a)")
    ]
    cases_b = {_case_id(c): c for c in _cases(seg_b.payload)}
    for case_a in _cases(seg_a.payload):
        case_id = _case_id(case_a)
        case_b = cases_b.get(case_id)
        if case_b is None:
            lines.append(f"{case_id}  only in A")
            continue
        raw = _equal(
            _hash(_first(case_a, "raw_output_sha256")), _hash(_first(case_b, "raw_output_sha256"))
        )
        totals["cases"] += 1
        totals["same_outcome"] += _outcome(case_a) == _outcome(case_b)
        totals["same_status"] += case_a.get("status") == case_b.get("status")
        totals["hash_comparable"] += raw != "n/a"
        totals["hash_equal"] += raw == "equal"
        lines.append(
            f"{case_id}  A={_outcome(case_a)}  B={_outcome(case_b)}  raw_hash={raw}  "
            f"violations A={_violations(case_a)}  B={_violations(case_b)}"
        )
    return lines


def _llm_section(a: Run, b: Run) -> list[str]:
    lines = ["", "== LLM tier (M3): outcome, raw-output hash and violations per case"]
    if not a.segments or not b.segments:
        missing = [side for side, run in (("A", a), ("B", b)) if not run.segments]
        lines.append(f"no LLM tier on side {' and '.join(missing)}; nothing to compare")
        return lines
    tags_a = list(dict.fromkeys(s.tag for s in a.segments))
    tags_b = list(dict.fromkeys(s.tag for s in b.segments))
    unrecorded = [side for side, tags in (("A", tags_a), ("B", tags_b)) if None in tags]
    if unrecorded:
        lines.append(
            f"the Ollama image tag is not recorded on side {' and '.join(unrecorded)} "
            "(no segment.json); such segments are paired only with unrecorded ones, by number"
        )
    lines += [f"tag {tag}: only on A" for tag in tags_a if tag is not None and tag not in tags_b]
    lines += [f"tag {tag}: only on B" for tag in tags_b if tag is not None and tag not in tags_a]
    for tag in (t for t in tags_a if t in tags_b):
        name = "not recorded" if tag is None else tag
        segs_a = {s.repeat_index: s for s in a.segments if s.tag == tag}
        segs_b = {s.repeat_index: s for s in b.segments if s.tag == tag}
        totals = dict.fromkeys(
            ("cases", "same_outcome", "same_status", "hash_comparable", "hash_equal"), 0
        )
        pairs = 0
        for index in sorted(set(segs_a) | set(segs_b)):
            seg_a, seg_b = segs_a.get(index), segs_b.get(index)
            if seg_a is None or seg_b is None:
                lines.append(f"tag {name} repeat {index}: only on {'A' if seg_b is None else 'B'}")
                continue
            pairs += 1
            lines += _pair_lines(seg_a, seg_b, name, totals)
        lines.append(
            f"tag {name} summary: {pairs} segment pair(s), {totals['cases']} cases; "
            f"same status {totals['same_status']}; same end-to-end outcome "
            f"{totals['same_outcome']}; raw-output hash equal {totals['hash_equal']} "
            f"of {totals['hash_comparable']} comparable"
        )
    return lines


def compare(path_a: Path, path_b: Path) -> list[str]:
    run_a, run_b = load_run(path_a, "A"), load_run(path_b, "B")
    lines = [*_header("A", run_a), *_header("B", run_b)]
    lines += _oracle_section(run_a, run_b)
    lines += _llm_section(run_a, run_b)
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.d8_compare",
        description="Compare two D8 run directories case by case (no raw model text is read).",
    )
    parser.add_argument("run_a", type=Path)
    parser.add_argument("run_b", type=Path)
    arguments = parser.parse_args(argv)
    try:
        lines = compare(arguments.run_a, arguments.run_b)
    except CompareRefused as refusal:
        print(f"D8 COMPARE REFUSED: {refusal}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
