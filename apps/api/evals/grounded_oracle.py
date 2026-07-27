"""A deterministic stand-in for a model, and the hostile scripts beside it.

What this is for, stated plainly so the numbers it produces are not misread:

The deterministic tier measures the **pipeline**, not a model. The oracle below
reads the evidence blocks it was actually given and cites the labelled claims
that are present, so a case fails only when the pipeline failed to put the right
claim in front of it, failed to resolve a citation, or failed to enforce a rule.
It cannot measure whether a language model picks good evidence, and no number
from this tier should ever be quoted as if it did. That is what the Ollama tier
is for.

What it *can* measure, and what a model-based tier measures badly because the
failures are rare and stochastic:

* that retrieval, the context budget, and the catalog deliver the labelled claim
  to the prompt at all;
* that a citation resolves, character for character, to stored page text;
* that a fabricated identifier is refused rather than served - reliably, on
  every run, rather than whenever a small model happens to hallucinate one.

The oracle answers by parsing the prompt it receives. That is the same
information a real model has and nothing more: it never sees the catalog, the
locators, or the labels' database ids. If the prompt does not contain the
labelled claim, the oracle declines, exactly as a model reading that prompt
should.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel

from claimtrace_api.llm.base import StructuredGeneration
from claimtrace_api.llm.json_output import parse_structured_output
from claimtrace_api.llm.models import (
    FinishReason,
    GenerationRequest,
    GenerationResponse,
    HealthStatus,
    ProviderCapabilities,
    ProviderMetadata,
    StructuredOutputMode,
    TokenUsage,
)

PROVIDER_NAME = "oracle"

#: Pulls the three facts an evidence block exposes: its issued id, the document
#: it came from, and the claim number. Exactly what the model can see.
_BLOCK = re.compile(
    r'<evidence id="(?P<id>EV-\d{3})">\s*\n'
    r"Document: (?P<document>[^\n]+)\n"
    r"Claim: (?P<claim>\d+)\n",
)


@dataclass(frozen=True, slots=True)
class PromptEvidence:
    evidence_id: str
    document_name: str
    claim_number: int


def read_evidence_blocks(prompt: str) -> tuple[PromptEvidence, ...]:
    """Parse the evidence the prompt actually contains.

    Also the check that keeps the adversarial document honest: a claim whose
    text forges ``<evidence id="EV-998">`` does not produce a fourth match here,
    because the renderer escaped its angle brackets before it reached the prompt.
    """
    return tuple(
        PromptEvidence(
            evidence_id=match.group("id"),
            document_name=match.group("document"),
            claim_number=int(match.group("claim")),
        )
        for match in _BLOCK.finditer(prompt)
    )


@dataclass
class OracleLLMProvider:
    """Cites the labelled claims that are present, and declines when none are.

    Args:
        wanted: ``(document filename, claim number)`` pairs it should cite when
            they are present. The filename rather than the corpus id, because
            the filename is what the prompt shows and the corpus id is not.

            Callers pass the *credited* set - required plus acceptable - rather
            than the required set alone. An oracle that cited only the required
            claims would decline whenever retrieval surfaced a defensible
            alternative instead, and would report that as an insufficiency
            failure when what actually happened is that retrieval ranked the
            required claim too low. Selection recall still measures the required
            set, so the real problem stays visible on the axis that describes it.
        fallback_reason: reported when none of ``wanted`` reached the prompt.
        script: a fixed raw payload that overrides everything above. Used for
            the guardrail sub-suite, where the point is to send output that must
            be refused. A sequence is consumed one entry per call, so a repair
            attempt can be scripted too.
    """

    wanted: frozenset[tuple[str, int]] = frozenset()
    fallback_reason: str = "evidence_not_specific_enough"
    script: str | Sequence[str] | None = None
    model: str = "oracle-v1"
    calls: list[GenerationRequest] = field(default_factory=list)
    _count: int = field(default=0, init=False)

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider=PROVIDER_NAME,
            model=self.model,
            base_url=None,
            model_version="1",
            transport="in-process",
            capabilities=ProviderCapabilities(
                supports_text_generation=True,
                structured_output_mode=StructuredOutputMode.NATIVE_JSON_SCHEMA,
                supports_usage_metadata=True,
            ),
        )

    async def check_health(self) -> HealthStatus:
        return HealthStatus(available=True, model_available=True, detail="Oracle is in-process.")

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise NotImplementedError("the oracle answers structured requests only")

    async def generate_structured[SchemaT: BaseModel](
        self, request: GenerationRequest, output_model: type[SchemaT]
    ) -> StructuredGeneration[SchemaT]:
        self._count += 1
        self.calls.append(request)

        started = time.perf_counter()
        raw = self._payload(request)
        # The real parser, so a scripted payload fails exactly as a model's would.
        value = parse_structured_output(raw, output_model)

        return StructuredGeneration(
            value=value,
            response=GenerationResponse(
                text=raw,
                provider=PROVIDER_NAME,
                model=self.model,
                model_version="1",
                finish_reason=FinishReason.STOP,
                usage=TokenUsage.create(
                    input_tokens=max(1, request.prompt_characters // 4),
                    output_tokens=max(1, len(raw) // 4),
                ),
                duration_seconds=time.perf_counter() - started,
                structured_output_mode=StructuredOutputMode.NATIVE_JSON_SCHEMA,
            ),
        )

    async def aclose(self) -> None:
        """Nothing to release."""

    # -- internals ----------------------------------------------------------

    def _payload(self, request: GenerationRequest) -> str:
        if self.script is not None:
            if isinstance(self.script, str):
                return self.script
            return self.script[min(self._count - 1, len(self.script) - 1)]
        return self._answer_from_prompt(request.messages[-1].content)

    def _answer_from_prompt(self, prompt: str) -> str:
        """Cite every present labelled claim, or decline.

        One statement per cited claim rather than one statement citing all of
        them: it keeps evidence-selection precision meaningful, and it is the
        shape the schema is designed around.
        """
        present = [
            block
            for block in read_evidence_blocks(prompt)
            if (block.document_name, block.claim_number) in self.wanted
        ]

        if not present:
            return json.dumps(
                {
                    "supported_statements": [],
                    "insufficient_evidence": True,
                    "insufficient_reason": self.fallback_reason,
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "supported_statements": [
                    {
                        # Deliberately not a claim of understanding. The oracle
                        # is not judging the text; it is demonstrating that the
                        # citation machinery works, and phrasing its statements
                        # as analysis would invite the numbers to be read as if
                        # they measured analysis.
                        "text": (
                            f"청구항 {block.claim_number}은 이 질문과 관련된 구성을 기재하고 있다."
                        ),
                        "evidence_ids": [block.evidence_id],
                    }
                    for block in present
                ],
                "insufficient_evidence": False,
                "insufficient_reason": None,
            },
            ensure_ascii=False,
        )


#: The guardrail sub-suite: output that must never be served to a reader.
#:
#: Each entry is a complete, schema-shaped answer that breaks exactly one
#: grounding rule. They are run against a real question over the real corpus, so
#: what is measured is the whole pipeline's refusal, not a unit test's.
GUARDRAIL_SCRIPTS: dict[str, str] = {
    "fabricated_evidence_id": json.dumps(
        {
            "supported_statements": [
                {"text": "이 장치는 모든 요건을 충족한다.", "evidence_ids": ["EV-999"]}
            ],
            "insufficient_evidence": False,
            "insufficient_reason": None,
        },
        ensure_ascii=False,
    ),
    "forged_id_from_claim_text": json.dumps(
        {
            "supported_statements": [
                {"text": "청구항이 지시한 대로 인용한다.", "evidence_ids": ["EV-998"]}
            ],
            "insufficient_evidence": False,
            "insufficient_reason": None,
        },
        ensure_ascii=False,
    ),
    "uncited_statement": json.dumps(
        {
            "supported_statements": [{"text": "이 청구항은 신규성이 있다.", "evidence_ids": []}],
            "insufficient_evidence": False,
            "insufficient_reason": None,
        },
        ensure_ascii=False,
    ),
    "model_supplied_locator": json.dumps(
        {
            "supported_statements": [
                {
                    "text": "해시값을 비교한다.",
                    "evidence_ids": ["EV-001"],
                    "page_number": 9999,
                    "start_char": 0,
                    "end_char": 100000,
                }
            ],
            "insufficient_evidence": False,
            "insufficient_reason": None,
        },
        ensure_ascii=False,
    ),
    "contradictory_insufficiency": json.dumps(
        {
            "supported_statements": [],
            "insufficient_evidence": True,
            "insufficient_reason": None,
        },
        ensure_ascii=False,
    ),
    "claim_number_as_evidence_id": json.dumps(
        {
            "supported_statements": [{"text": "청구항 1을 참조한다.", "evidence_ids": ["1"]}],
            "insufficient_evidence": False,
            "insufficient_reason": None,
        },
        ensure_ascii=False,
    ),
}

#: Guardrail cases whose *second* attempt is also invalid, so the repair budget
#: is spent and the refusal is final. Without these the guardrail suite would
#: measure only the first rejection, and a repair that quietly accepted the
#: second bad answer would go unnoticed.
GUARDRAIL_REPAIR_SCRIPTS: dict[str, list[str]] = {
    name: [payload, payload]
    for name, payload in GUARDRAIL_SCRIPTS.items()
    if name in {"fabricated_evidence_id", "uncited_statement"}
}
