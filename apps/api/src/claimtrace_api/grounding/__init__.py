"""Evidence-grounded generation (Phase 4A-2).

This package holds the parts of grounded answering that have no business
touching a database, an HTTP request, or a provider:

* :mod:`evidence` - the request-local evidence catalog and the opaque evidence
  identifier that is the *only* thing the model is allowed to choose.
* :mod:`context` - the deterministic prompt builder and its context budget.
* :mod:`draft` - the strict Pydantic schema the model's answer must satisfy.
* :mod:`validation` - the post-generation check that turns a draft into
  something the server is willing to say, or rejects it outright.

The orchestration that wires these to retrieval and to a provider lives in
``claimtrace_api.services.grounded_generation``. Keeping the rules here means
they can be tested without a database, a model, or a network, which is what
makes the citation-integrity tests cheap enough to be exhaustive.
"""
