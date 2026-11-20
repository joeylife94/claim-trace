"""Opt-in diagnostics capture for the grounded-generation evaluation.

D8-01 recorded that most real-model cases ended in ``502 grounded_repair_failed``
and nothing that says why: the harness runs at log level WARNING, so the product's
own per-attempt violation log was dropped, and Ollama's ``done_reason`` and token
counts never left the provider. This module records those facts **from the
harness**, without touching the product:

* :class:`RecordingProvider` wraps whatever sits in ``app.state.llm_provider`` and
  notes each ``generate_structured`` call (messages, options, outcome).
* :class:`RecordingTransport` wraps the ``httpx`` transport under an injected
  ``OllamaProvider`` and notes the raw ``/api/chat`` exchange.
* :func:`capture_rejections` attaches a log handler that reads only the violation
  enum and attempt number from the product's ``"grounded output rejected"`` record.

Two kinds of output come back out, and the separation is the point:

* :meth:`DiagnosticsRecorder.case_block` is **content free**: counts, durations,
  hashes, closed-set codes, evidence labels. It may sit in ``results-<tier>.json``.
* :meth:`DiagnosticsRecorder.raw_document` holds prompts and raw model output. That
  is untrusted text about confidential-style material; it is written only to
  ``diagnostics-<tier>.json`` and must never be rendered as Markdown or HTML.

Nothing here changes what a provider returns or raises.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import re
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel

from claimtrace_api.grounding.validation import GroundedViolation
from claimtrace_api.llm.base import LLMProvider, StructuredGeneration
from claimtrace_api.llm.models import (
    GenerationRequest,
    GenerationResponse,
    HealthStatus,
    ProviderMetadata,
)

SCHEMA_VERSION = 1

#: Bounds on what is stored. Characters, not bytes.
MAX_USER_PROMPT_CHARACTERS = 32768
MAX_RAW_OUTPUT_CHARACTERS = 16384
MAX_ERROR_DETAIL_CHARACTERS = 500
MAX_DONE_REASON_CHARACTERS = 32

UNTRUSTED_NOTICE = (
    "Prompts and model output below are untrusted text. Never render them as Markdown or HTML."
)

#: The product logger whose INFO record carries the violation, and its message.
GROUNDING_LOGGER = "claimtrace_api.services.grounded_generation"
REJECTION_MESSAGE = "grounded output rejected"

_CHAT_PATH = "/api/chat"

_VIOLATIONS = frozenset(violation.value for violation in GroundedViolation)

#: Exactly what ``_render_evidence_block`` writes. Claim text and the question are
#: HTML-escaped before they reach the prompt, so neither can forge a block header.
_EVIDENCE_BLOCK = re.compile(
    r'<evidence id="(?P<id>EV-\d{3})">\n'
    r"Document: (?P<document>[^\n]*)\n"
    r"Claim: (?P<claim>\d+)\n"
)


# -- small helpers ----------------------------------------------------------


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cut(text: str, limit: int) -> tuple[str, bool]:
    return (text[:limit], True) if len(text) > limit else (text, False)


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _nanoseconds_to_ms(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return round(value / 1e6, 1)


def prompt_digest(messages: Sequence[tuple[str, str]]) -> str:
    """SHA-256 of the whole prompt, as the data contract defines it."""
    encoded = json.dumps(
        [[role, content] for role, content in messages],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256_text(encoded)


def parse_catalog(user_prompt: str, corpus_ids: Mapping[str, str]) -> list[dict[str, Any]]:
    """The evidence the model was shown, read back out of the prompt.

    The filename is un-escaped and mapped to the corpus id; one that is not in the
    corpus is kept as the filename.
    """
    entries: list[dict[str, Any]] = []
    for match in _EVIDENCE_BLOCK.finditer(user_prompt):
        filename = html.unescape(match.group("document"))
        entries.append(
            {
                "evidence_id": match.group("id"),
                "document": corpus_ids.get(filename, filename),
                "claim_number": int(match.group("claim")),
            }
        )
    return entries


# -- records ----------------------------------------------------------------


@dataclass(slots=True)
class HttpExchange:
    """One HTTP round trip to the model server."""

    status: int | None
    wall_seconds: float
    body_bytes: int | None = None
    done_reason: str | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    total_ms: float | None = None
    load_ms: float | None = None
    prompt_eval_ms: float | None = None
    eval_ms: float | None = None
    #: ``message.content`` exactly as the server returned it. Raw text.
    content: str | None = None

    def as_raw(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "wall_seconds": round(self.wall_seconds, 3),
            "done_reason": self.done_reason,
            "prompt_eval_count": self.prompt_eval_count,
            "eval_count": self.eval_count,
            "total_ms": self.total_ms,
            "load_ms": self.load_ms,
            "prompt_eval_ms": self.prompt_eval_ms,
            "eval_ms": self.eval_ms,
            "body_bytes": self.body_bytes,
        }


@dataclass(slots=True)
class CallRecord:
    """One ``generate`` / ``generate_structured`` call."""

    attempt: int
    messages: tuple[tuple[str, str], ...]
    num_predict: int | None
    temperature: float | None
    started: float
    wall_seconds: float = 0.0
    finished: bool = False
    #: The provider's own text, used when no HTTP exchange carried content (the
    #: oracle tier).
    response_text: str | None = None
    errored: bool = False
    error_code: str | None = None
    exchanges: list[HttpExchange] = field(default_factory=list)

    @property
    def system_prompt(self) -> str | None:
        for role, content in self.messages:
            if role == "system":
                return content
        return None

    @property
    def user_prompt(self) -> str:
        return "\n\n".join(content for role, content in self.messages if role != "system")

    @property
    def raw_output(self) -> str | None:
        for exchange in reversed(self.exchanges):
            if exchange.content is not None:
                return exchange.content
        return self.response_text

    @property
    def last_ok_exchange(self) -> HttpExchange | None:
        for exchange in reversed(self.exchanges):
            if exchange.status == 200:
                return exchange
        return None


@dataclass(slots=True)
class CaseRecord:
    case_id: str
    calls: list[CallRecord] = field(default_factory=list)
    #: attempt index -> violation value
    rejections: dict[int, str] = field(default_factory=dict)
    status: int | None = None
    body: Any = None


class DiagnosticsRecorder:
    """Collects what happened inside each case, for both output files."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cases: list[CaseRecord] = []
        self._current: CaseRecord | None = None
        self._call: CallRecord | None = None
        self.format_schema_sha256: str | None = None

    # -- recording --------------------------------------------------------

    def begin_case(self, case_id: str) -> None:
        with self._lock:
            self._current = CaseRecord(case_id=case_id)
            self._call = None
            self._cases.append(self._current)

    def end_case(self, *, status: int | None = None, body: Any = None) -> None:
        with self._lock:
            if self._current is not None:
                self._current.status = status
                self._current.body = body
            self._current = None
            self._call = None

    def begin_call(self, request: GenerationRequest) -> None:
        with self._lock:
            if self._current is None:
                return
            self._call = CallRecord(
                attempt=len(self._current.calls),
                messages=tuple((m.role.value, m.content) for m in request.messages),
                num_predict=request.options.max_output_tokens,
                temperature=request.options.temperature,
                started=time.perf_counter(),
            )
            self._current.calls.append(self._call)

    def end_call(
        self,
        response: GenerationResponse | None = None,
        error: BaseException | None = None,
    ) -> None:
        with self._lock:
            call = self._call
            self._call = None
            if call is None:
                return
            call.wall_seconds = time.perf_counter() - call.started
            call.finished = True
            if response is not None:
                call.response_text = response.text
            if error is not None:
                call.errored = True
                code = getattr(error, "code", None)
                value = getattr(code, "value", None)
                call.error_code = value if isinstance(value, str) else None

    def add_http_exchange(self, exchange: HttpExchange) -> None:
        with self._lock:
            if self._call is not None:
                self._call.exchanges.append(exchange)

    def set_format_schema(self, schema: object) -> None:
        with self._lock:
            if self.format_schema_sha256 is None:
                encoded = json.dumps(
                    schema, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                )
                self.format_schema_sha256 = sha256_text(encoded)

    def add_rejection(self, violation: object, repair_attempt: object) -> None:
        """Record the product's own verdict. Only closed-set values are kept."""
        if not isinstance(violation, str) or violation not in _VIOLATIONS:
            return
        if not isinstance(repair_attempt, int) or isinstance(repair_attempt, bool):
            return
        with self._lock:
            if self._current is not None:
                self._current.rejections[repair_attempt] = violation

    # -- reading ----------------------------------------------------------

    def violations(self, case_id: str) -> list[str]:
        """The content-free violation sequence of the most recent case with this id."""
        with self._lock:
            record = self._find(case_id)
            if record is None:
                return []
            return [record.rejections[index] for index in sorted(record.rejections)]

    def _find(self, case_id: str) -> CaseRecord | None:
        for record in reversed(self._cases):
            if record.case_id == case_id:
                return record
        return None

    def case_ids(self) -> list[str]:
        with self._lock:
            return [record.case_id for record in self._cases]

    def case_blocks(self, corpus_ids: Mapping[str, str]) -> dict[str, dict[str, Any]]:
        with self._lock:
            records = list(self._cases)
        return {record.case_id: self._block(record, corpus_ids) for record in records}

    def case_block(
        self,
        case_id: str,
        corpus_ids: Mapping[str, str],
        response_body: Any = None,
        status: int | None = None,
    ) -> dict[str, Any]:
        """Contract section A for one case. Content free."""
        with self._lock:
            record = self._find(case_id) or CaseRecord(case_id=case_id)
        return self._block(
            record,
            corpus_ids,
            body=record.body if response_body is None else response_body,
            status=record.status if status is None else status,
        )

    def _block(
        self,
        record: CaseRecord,
        corpus_ids: Mapping[str, str],
        *,
        body: Any = None,
        status: int | None = None,
    ) -> dict[str, Any]:
        body = record.body if body is None else body
        status = record.status if status is None else status
        calls = record.calls
        return {
            "schema_version": SCHEMA_VERSION,
            "error_detail": _error_detail(body, status),
            "repair_used": len(calls) >= 2,
            "catalog": parse_catalog(calls[0].user_prompt, corpus_ids) if calls else [],
            "generation": _generation(body, status),
            "attempts": [
                _attempt_block(index, call, record, is_last=index == len(calls) - 1)
                for index, call in enumerate(calls)
            ],
        }

    def raw_document(self, tier: str) -> dict[str, Any]:
        """Contract section B. Raw, untrusted text: never render it."""
        with self._lock:
            records = list(self._cases)
            format_sha = self.format_schema_sha256
        system_prompts: dict[str, str] = {}
        cases: list[dict[str, Any]] = []
        for record in records:
            calls: list[dict[str, Any]] = []
            for call in record.calls:
                system = call.system_prompt
                system_sha = None
                if system is not None:
                    system_sha = sha256_text(system)
                    system_prompts.setdefault(system_sha, system)
                user_prompt, user_truncated = _cut(call.user_prompt, MAX_USER_PROMPT_CHARACTERS)
                raw = call.raw_output
                raw_text, raw_truncated = (
                    _cut(raw, MAX_RAW_OUTPUT_CHARACTERS) if raw is not None else (None, False)
                )
                calls.append(
                    {
                        "attempt": call.attempt,
                        "system_prompt_sha256": system_sha,
                        "user_prompt": user_prompt,
                        "user_prompt_truncated": user_truncated,
                        "raw_output": raw_text,
                        "raw_output_truncated": raw_truncated,
                        "raw_output_sha256": sha256_text(raw) if raw is not None else None,
                        "http": [exchange.as_raw() for exchange in call.exchanges],
                    }
                )
            cases.append({"id": record.case_id, "calls": calls})
        return {
            "schema_version": SCHEMA_VERSION,
            "tier": tier,
            "notice": UNTRUSTED_NOTICE,
            "system_prompts": system_prompts,
            "format_schema_sha256": format_sha,
            "cases": cases,
        }


def _error_detail(body: Any, status: int | None) -> str | None:
    if status is None or status == 200 or not isinstance(body, dict):
        return None
    detail = body.get("detail")
    if not isinstance(detail, str):
        return None
    return detail[:MAX_ERROR_DETAIL_CHARACTERS]


def _generation(body: Any, status: int | None) -> dict[str, Any] | None:
    if status != 200 or not isinstance(body, dict):
        return None
    generation = body.get("generation")
    if not isinstance(generation, dict):
        return None
    usage = generation.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    return {
        "finish_reason": generation.get("finish_reason"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "attempts": generation.get("attempts"),
        "duration_seconds": generation.get("duration_seconds"),
    }


def _attempt_block(
    index: int, call: CallRecord, record: CaseRecord, *, is_last: bool
) -> dict[str, Any]:
    violation = record.rejections.get(index)
    if call.errored:
        outcome = "provider_error"
        violation = None
    elif violation is not None:
        outcome = "rejected"
    elif is_last and record.status == 200:
        outcome = "accepted"
    else:
        outcome = "not_validated"

    ok = call.last_ok_exchange
    raw = call.raw_output
    done_reason = ok.done_reason[:MAX_DONE_REASON_CHARACTERS] if ok and ok.done_reason else None
    return {
        "attempt": index,
        "outcome": outcome,
        "violation": violation,
        "provider_error_code": call.error_code,
        "http_calls": len(call.exchanges),
        "done_reason": done_reason,
        "prompt_eval_count": ok.prompt_eval_count if ok else None,
        "eval_count": ok.eval_count if ok else None,
        "total_ms": ok.total_ms if ok else None,
        "load_ms": ok.load_ms if ok else None,
        "prompt_eval_ms": ok.prompt_eval_ms if ok else None,
        "eval_ms": ok.eval_ms if ok else None,
        "wall_seconds": round(call.wall_seconds, 3),
        "prompt_characters": sum(len(content) for _, content in call.messages),
        "prompt_sha256": prompt_digest(call.messages),
        "response_characters": len(raw) if raw is not None else None,
        "raw_output_sha256": sha256_text(raw) if raw is not None else None,
        "num_predict": call.num_predict,
        "temperature": call.temperature,
    }


# -- provider wrapper -------------------------------------------------------


class RecordingProvider:
    """Delegates to ``inner`` and records each generation. Alters nothing."""

    def __init__(self, inner: LLMProvider, recorder: DiagnosticsRecorder) -> None:
        self._inner = inner
        self._recorder = recorder

    @property
    def inner(self) -> LLMProvider:
        return self._inner

    @property
    def name(self) -> str:
        return self._inner.name

    def get_metadata(self) -> ProviderMetadata:
        return self._inner.get_metadata()

    async def check_health(self) -> HealthStatus:
        return await self._inner.check_health()

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        self._recorder.begin_call(request)
        try:
            response = await self._inner.generate(request)
        except Exception as error:
            self._recorder.end_call(error=error)
            raise
        self._recorder.end_call(response=response)
        return response

    async def generate_structured[SchemaT: BaseModel](
        self, request: GenerationRequest, output_model: type[SchemaT]
    ) -> StructuredGeneration[SchemaT]:
        self._recorder.begin_call(request)
        try:
            result = await self._inner.generate_structured(request, output_model)
        except Exception as error:
            self._recorder.end_call(error=error)
            raise
        self._recorder.end_call(response=result.response)
        return result

    async def aclose(self) -> None:
        await self._inner.aclose()


# -- transport wrapper ------------------------------------------------------


class _ReplayStream(httpx.AsyncByteStream):
    def __init__(self, body: bytes) -> None:
        self._body = body

    async def __aiter__(self) -> Any:
        yield self._body

    async def aclose(self) -> None:
        return None


class RecordingTransport(httpx.AsyncBaseTransport):
    """Records ``POST /api/chat`` exchanges and hands back an equivalent response."""

    def __init__(self, inner: httpx.AsyncBaseTransport, recorder: DiagnosticsRecorder) -> None:
        self._inner = inner
        self._recorder = recorder

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or request.url.path != _CHAT_PATH:
            return await self._inner.handle_async_request(request)

        self._note_request(request)
        started = time.perf_counter()
        try:
            response = await self._inner.handle_async_request(request)
            raw = b"".join([chunk async for chunk in response.stream])  # type: ignore[union-attr]
            await response.stream.aclose()  # type: ignore[union-attr]
        except BaseException:
            self._recorder.add_http_exchange(
                HttpExchange(status=None, wall_seconds=time.perf_counter() - started)
            )
            raise
        wall = time.perf_counter() - started

        self._recorder.add_http_exchange(await self._exchange(response, raw, wall))
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=_ReplayStream(raw),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()

    def _note_request(self, request: httpx.Request) -> None:
        try:
            payload = json.loads(request.content)
            if isinstance(payload, dict) and "format" in payload:
                self._recorder.set_format_schema(payload["format"])
        except Exception:  # noqa: BLE001 - recording must never break a request
            return

    @staticmethod
    async def _exchange(response: httpx.Response, raw: bytes, wall: float) -> HttpExchange:
        exchange = HttpExchange(status=response.status_code, wall_seconds=wall, body_bytes=len(raw))
        if response.status_code != 200:
            return exchange
        try:
            # A separate copy, so decoding for the record never touches the
            # response that goes back to the provider.
            probe = httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                stream=_ReplayStream(raw),
            )
            await probe.aread()
            body = probe.json()
        except Exception:  # noqa: BLE001 - non-JSON bodies record status and size only
            return exchange
        if not isinstance(body, dict):
            return exchange

        done_reason = body.get("done_reason")
        if isinstance(done_reason, str):
            exchange.done_reason = done_reason[:MAX_DONE_REASON_CHARACTERS]
        exchange.prompt_eval_count = _optional_int(body.get("prompt_eval_count"))
        exchange.eval_count = _optional_int(body.get("eval_count"))
        exchange.total_ms = _nanoseconds_to_ms(body.get("total_duration"))
        exchange.load_ms = _nanoseconds_to_ms(body.get("load_duration"))
        exchange.prompt_eval_ms = _nanoseconds_to_ms(body.get("prompt_eval_duration"))
        exchange.eval_ms = _nanoseconds_to_ms(body.get("eval_duration"))
        message = body.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            exchange.content = message["content"]
        return exchange


# -- log capture ------------------------------------------------------------


class RejectionLogHandler(logging.Handler):
    """Reads the violation enum and attempt number from the product's log record.

    Nothing else is read from the record. The product never puts content in that
    record, and this handler would not copy it if it did.
    """

    def __init__(self, recorder: DiagnosticsRecorder, forward_to: logging.Logger | None) -> None:
        super().__init__(level=logging.INFO)
        self._recorder = recorder
        self._forward_to = forward_to

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.msg == REJECTION_MESSAGE:
                self._recorder.add_rejection(
                    getattr(record, "violation", None), getattr(record, "repair_attempt", None)
                )
            # The logger is lifted to INFO and detached from its parents while
            # capturing, so the harness stays as quiet as before. WARNING and
            # above are still passed on.
            if record.levelno >= logging.WARNING and self._forward_to is not None:
                self._forward_to.callHandlers(record)
        except Exception:  # noqa: BLE001 - a logging handler must never raise
            return


@contextmanager
def capture_rejections(recorder: DiagnosticsRecorder) -> Iterator[None]:
    """Capture rejection records for the duration of the block, then restore."""
    logger = logging.getLogger(GROUNDING_LOGGER)
    previous_level = logger.level
    previous_propagate = logger.propagate
    handler = RejectionLogHandler(recorder, forward_to=logger.parent)
    try:
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


# -- wiring -----------------------------------------------------------------


def _close_async_client(client: httpx.AsyncClient, test_client: Any) -> None:
    portal = getattr(test_client, "portal", None)
    if portal is not None:
        portal.call(client.aclose)
    else:
        asyncio.run(client.aclose())


@contextmanager
def recording_ollama_provider(
    test_client: Any,
    settings: Any,
    recorder: DiagnosticsRecorder,
    *,
    inner_transport: httpx.AsyncBaseTransport | None = None,
) -> Iterator[RecordingProvider]:
    """Put a recording ``OllamaProvider`` in ``app.state.llm_provider``.

    Built from the same settings and helpers as the production factory. The
    original provider goes back before the block ends, so the application's own
    shutdown closes it; the client created here is closed here. ``inner_transport``
    exists so tests can serve ``/api/chat`` from a mock; the harness leaves it unset.
    """
    from claimtrace_api.llm.ollama import OllamaProvider
    from claimtrace_api.llm.registry import build_retry_policy, build_timeouts

    timeouts = build_timeouts(settings)
    # trust_env is off because an environment proxy would be mounted ahead of the
    # recording transport and the exchange would silently go unrecorded.
    http_client = httpx.AsyncClient(
        base_url=settings.llm_ollama_base_url,
        timeout=timeouts.to_httpx(),
        transport=RecordingTransport(inner_transport or httpx.AsyncHTTPTransport(), recorder),
        trust_env=False,
    )
    inner = OllamaProvider(
        base_url=settings.llm_ollama_base_url,
        model=settings.llm_ollama_model,
        timeouts=timeouts,
        retry_policy=build_retry_policy(settings),
        client=http_client,
    )
    provider = RecordingProvider(inner, recorder)
    state = test_client.app.state
    original = state.llm_provider
    state.llm_provider = provider
    try:
        yield provider
    finally:
        state.llm_provider = original
        _close_async_client(http_client, test_client)
