---
status: proposed
contact: "@eavanvalkenburg"
date: 2026-09-01
deciders: ["@eavanvalkenburg"]
---

# Preserve provider refusals as typed Python content

## Context and Problem Statement

Python providers currently convert native refusal payloads into ordinary text content. The refusal
explanation remains readable in some paths, but its meaning is lost across response aggregation,
history, provider replay, hosting, and UI boundaries. Python needs a durable representation that
preserves refusal semantics without coupling providers to a shared conversion package.

## Decision Drivers

- Preserve native refusal semantics through streaming and non-streaming paths.
- Keep refusal explanations visible through existing message and response text APIs.
- Round-trip native refusal fields where a transport supports them.
- Preserve history through existing `Content.to_dict()` and `Content.from_dict()` behavior.
- Avoid a parallel content hierarchy or provider-wide parsing abstraction.

## Considered Options

- Add a `refusal` discriminator to the unified `Content` model and reuse its `text` field.
- Keep `type="text"` and record refusal state in `additional_properties`.
- Represent refusals as error content.
- Add a dedicated refusal content class hierarchy.

## Decision Outcome

Add `Content(type="refusal", text=...)` and `Content.from_refusal(...)`.

Refusal text participates in `Message.text`, response text, update text, and adjacent streaming
coalescing. Structured-output parsing continues to read only ordinary text, so a refusal is not
mistaken for a requested response model. A refusal is completed model output, not an execution
failure; response status and finish reason remain separate.

OpenAI Responses, OpenAI Chat Completions, and Responses-compatible hosting preserve native refusal
fields and events. Providers and protocols without a refusal content primitive serialize the
explanation as ordinary text while the Agent Framework object and durable history retain the
`refusal` discriminator.

This is a released core and OpenAI API, following those packages' existing lifecycle stage. Beta
and alpha hosting/UI packages retain their package-level lifecycle stage.

### Consequences

- Serialized refusal content has the additive shape `{"type": "refusal", "text": "..."}`.
- Existing stored refusals remain ordinary text because they carry no reliable migration signal.
- Older runtimes preserve the structurally open content mapping but may not aggregate or render its
  text until upgraded.
- Native providers can reconstruct their refusal wire representation from durable history without
  relying on non-serializable SDK objects.
- Non-native provider boundaries lose the refusal discriminator by design, but not its visible text.

### Rejected alternatives

Provider metadata on ordinary text is untyped and inconsistently preserved by hosting and UI
boundaries. Error content conflates successful model output with run failure; the current .NET
OpenAI hosting converter uses that mapping, but Python does not adopt it. A dedicated class
hierarchy adds a second model beside Python's existing discriminator-based `Content` without adding
capability.
