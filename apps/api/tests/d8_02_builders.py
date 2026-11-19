"""Builds D8-02 run directories (COMMON sections A-C) for the report and compare tests.

The directories are generated into a temporary folder rather than committed under
``tests/data``: the repository ignores ``data/`` folders, the api image ignores ``*.log``,
and the raw-text files (``diagnostics-*.json``, ``ollama-server.log``) exist here only to
prove that the report and compare tools never read them.

The base files are the committed real-provider July record, as in ``test_d8_report``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
COMMITTED = API_ROOT / "evals" / "results"
REAL_RETRIEVAL = COMMITTED / "results.json"
REAL_ORACLE = COMMITTED / "grounded" / "results-deterministic.json"
REAL_OLLAMA = COMMITTED / "grounded" / "results-ollama.json"
MODEL = "qwen2.5:1.5b"

RULES = (
    "contradictory_insufficiency",
    "no_supported_statements",
    "unknown_evidence_id",
    "malformed_evidence_id",
)

CPU: dict[str, Any] = {
    "model_name": "Intel(R) Xeon(R) Platinum 8370C CPU @ 2.80GHz",
    "vendor_id": "GenuineIntel",
    "cpu_family": "6",
    "model": "106",
    "stepping": "6",
    "microcode": "0xffffffff",
    "cpu_cores": 2,
    "siblings": 4,
    "cache_size": "55296 KB",
    "flags_selected": ["sse4_2", "avx", "avx2", "fma", "avx512f", "avx512_vnni"],
    "flags_sha256": "a" * 64,
    "cpu_fingerprint": "0123456789abcdef" + "b" * 48,
}

ENVIRONMENT: dict[str, Any] = {
    "git_sha": "0123456789abcdef0123456789abcdef01234567",
    "run_id": "9999",
    "run_attempt": "1",
    "event_name": "workflow_dispatch",
    "runner": {
        "nproc": 4,
        "mem_total_mb": 15990,
        "os": "Ubuntu 24.04.1 LTS",
        "cpu": CPU,
        "kernel": "6.8.0-1017-azure",
        "image_os": "ubuntu24",
        "image_version": "20261110.1.0",
    },
    "api_image_id": "sha256:aaaa",
    "ollama_image_digest": "ollama/ollama@sha256:bbbb",
    "ollama_version": "0.40.16",
    "ollama_model": MODEL,
    "ollama_model_id": "65ec06548149",
    "embedding_model": "intfloat/multilingual-e5-small",
    "embedding_model_revision": "deadbeef",
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def catalog_for(case_id: str, variant: str) -> list[dict[str, Any]]:
    """A stand-in evidence catalog; ``variant`` changes the first entry."""
    first = 4 if variant == "a" else 5
    return [
        {"evidence_id": "EV-001", "document": "collector", "claim_number": first},
        {"evidence_id": "EV-002", "document": "thermal", "claim_number": 2},
    ]


def attempt(
    number: int,
    outcome: str,
    violation: str | None,
    *,
    ollama: bool,
    prompt_hash: str,
    raw_hash: str,
    done_reason: str = "stop",
    prompt_tokens: int = 800,
    output_tokens: int = 140,
) -> dict[str, Any]:
    return {
        "attempt": number,
        "outcome": outcome,
        "violation": violation,
        "provider_error_code": None,
        "http_calls": 1 if ollama else 0,
        "done_reason": done_reason if ollama else None,
        "prompt_eval_count": prompt_tokens if ollama else None,
        "eval_count": output_tokens if ollama else None,
        "total_ms": 21000.5 if ollama else None,
        "load_ms": 12.1 if ollama else None,
        "prompt_eval_ms": 9000.0 if ollama else None,
        "eval_ms": 11900.0 if ollama else None,
        "wall_seconds": 21.1,
        "prompt_characters": 2710,
        "prompt_sha256": prompt_hash,
        "response_characters": 455,
        "raw_output_sha256": raw_hash,
        "num_predict": 1024,
        "temperature": 0.0,
    }


RawVariant = Callable[[str | None, int, str], str]
Outcome = Callable[[str | None, int, str, dict[str, Any]], bool]


def _diagnostics(
    case: dict[str, Any],
    *,
    tier: str,
    tag: str | None,
    repeat_index: int,
    raw_variant: RawVariant,
    catalog_variant: str,
    done_reason: str,
    prompt_tokens: int,
) -> dict[str, Any]:
    case_id = str(case["id"])
    ollama = tier == "ollama"
    prompt_hash = sha(f"prompt|{case_id}|{catalog_variant}")

    def raw(attempt_number: int) -> str:
        return sha(f"raw|{raw_variant(tag, repeat_index, case_id)}|{case_id}|{attempt_number}")

    failed = case["status"] != 200
    index = sum(map(ord, case_id)) % len(RULES)
    if failed:
        attempts = [
            attempt(
                0,
                "rejected",
                RULES[index],
                ollama=ollama,
                prompt_hash=prompt_hash,
                raw_hash=raw(0),
                done_reason=done_reason,
                prompt_tokens=prompt_tokens,
            ),
            attempt(
                1,
                "rejected",
                RULES[(index + 1) % len(RULES)],
                ollama=ollama,
                prompt_hash=sha(f"repair|{case_id}"),
                raw_hash=raw(1),
                done_reason=done_reason,
                prompt_tokens=prompt_tokens + 200,
            ),
        ]
    else:
        attempts = [
            attempt(
                0,
                "accepted",
                None,
                ollama=ollama,
                prompt_hash=prompt_hash,
                raw_hash=raw(0),
                done_reason=done_reason,
                prompt_tokens=prompt_tokens,
            )
        ]
    return {
        "schema_version": 1,
        "error_detail": "grounded repair failed" if failed else None,
        "repair_used": failed,
        "catalog": catalog_for(case_id, catalog_variant),
        "generation": None
        if failed
        else {
            "finish_reason": "stop",
            "input_tokens": prompt_tokens,
            "output_tokens": 140,
            "attempts": 1,
            "duration_seconds": 21.4,
        },
        "attempts": attempts,
    }


def _default_raw(tag: str | None, repeat_index: int, case_id: str) -> str:
    return "same"


def _default_outcome(tag: str | None, repeat_index: int, case_id: str, case: dict[str, Any]) -> bool:
    return case["status"] == 200


def _grounded_payload(
    source: Path,
    *,
    tier: str,
    tag: str | None,
    repeat_index: int,
    diagnostics: bool,
    raw_variant: RawVariant,
    catalog_variant: str,
    done_reason: str,
    prompt_tokens: int,
    outcome: Outcome,
) -> dict[str, Any]:
    payload = read_json(source)
    for case in payload["per_case"]:
        if tier == "ollama":
            case["end_to_end_success"] = outcome(tag, repeat_index, str(case["id"]), case)
        if diagnostics:
            case["diagnostics"] = _diagnostics(
                case,
                tier=tier,
                tag=tag,
                repeat_index=repeat_index,
                raw_variant=raw_variant,
                catalog_variant=catalog_variant,
                done_reason=done_reason,
                prompt_tokens=prompt_tokens,
            )
    return payload


def build_run(
    root: Path,
    *,
    tags: list[str] | None = None,
    diagnostics: bool = True,
    raw_variant: RawVariant = _default_raw,
    outcome: Outcome = _default_outcome,
    catalog_variant: str = "a",
    oracle_only: bool = False,
    legacy_repeats: int = 2,
    environment: dict[str, Any] | None = None,
    context_length: int | None = 4096,
    done_reason: str = "stop",
    prompt_tokens: int = 800,
    raw_files: str | None = None,
    name: str = "run",
) -> Path:
    """A run directory.

    ``tags`` lists the segments in execution order (``["A", "B", "A", "B"]``); with
    ``tags=None`` the directory has ``legacy_repeats`` repeats and no ``segment.json``.
    ``raw_files`` is a sentinel written into the raw-text files that the tools must not read.
    """
    run = root / name
    (run / "retrieval").mkdir(parents=True)
    shutil.copy(REAL_RETRIEVAL, run / "retrieval" / "results.json")
    write_json(
        run / "grounded" / "results-deterministic.json",
        _grounded_payload(
            REAL_ORACLE,
            tier="deterministic",
            tag=None,
            repeat_index=1,
            diagnostics=diagnostics,
            raw_variant=raw_variant,
            catalog_variant=catalog_variant,
            done_reason=done_reason,
            prompt_tokens=prompt_tokens,
            outcome=outcome,
        ),
    )
    env = json.loads(json.dumps(environment or ENVIRONMENT))
    if oracle_only:
        for key in ("ollama_image_digest", "ollama_version", "ollama_model", "ollama_model_id"):
            env[key] = None
    segments = [] if oracle_only else (tags if tags is not None else [None] * legacy_repeats)
    seen: dict[str | None, int] = {}
    runtimes: list[dict[str, Any]] = []
    for number, tag in enumerate(segments, start=1):
        seen[tag] = seen.get(tag, 0) + 1
        folder = run / "grounded" / f"r{number}"
        write_json(
            folder / "results-ollama.json",
            _grounded_payload(
                REAL_OLLAMA,
                tier="ollama",
                tag=tag,
                repeat_index=seen[tag],
                diagnostics=diagnostics,
                raw_variant=raw_variant,
                catalog_variant=catalog_variant,
                done_reason=done_reason,
                prompt_tokens=prompt_tokens,
                outcome=outcome,
            ),
        )
        if tag is not None:
            version = tag
            write_json(
                folder / "segment.json",
                {
                    "schema_version": 1,
                    "segment": number,
                    "ollama_image_tag": tag,
                    "ollama_image_digest": f"ollama/ollama@sha256:{tag}",
                    "ollama_version": version,
                    "repeat_index": seen[tag],
                    "context_length_setting": None,
                    "started_at": "2026-11-19T10:00:00+00:00",
                    "finished_at": "2026-11-19T10:20:00+00:00",
                },
            )
            write_json(
                folder / "ollama-runtime.json",
                {
                    "schema_version": 1,
                    "api_version": version,
                    "ps": [
                        {
                            "name": MODEL,
                            "digest": "65ec06548149",
                            "size": 1,
                            "size_vram": 0,
                            "context_length": context_length,
                        }
                    ],
                    "show": {
                        "parameters": None,
                        "details": {},
                        "context_length": 32768,
                        "template_sha256": None,
                    },
                },
            )
            if not any(r["tag"] == tag for r in runtimes):
                runtimes.append(
                    {"tag": tag, "digest": f"ollama/ollama@sha256:{tag}", "version": version}
                )
        if raw_files:
            write_json(
                folder / "diagnostics-ollama.json",
                {"cases": [{"id": "g01", "calls": [{"raw_output": raw_files}]}]},
            )
            (folder / "ollama-server.log").write_text(f"{raw_files}\n", encoding="utf-8")
    if tags is not None and not oracle_only:
        env["ollama_runtimes"] = runtimes
        env["ollama_image_tag"] = tags[0]
        env["ollama_context_length_setting"] = None
    if diagnostics:
        env["diagnostics_captured"] = True
    write_json(run / "ENVIRONMENT.json", env)
    return run
