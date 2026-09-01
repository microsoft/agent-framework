---
status: proposed
contact: "@eavanvalkenburg"
date: 2026-09-01
deciders: ["@eavanvalkenburg"]
---

# Preserve model refusals with marked Python text content

## Context and Problem Statement

Refusals are provider/model-created output rather than framework execution errors. Python currently
converts native refusal payloads into ordinary text, which keeps the explanation visible but loses
the semantic across history, provider replay, Responses-compatible hosting, and DevUI. The framework
needs a reversible representation without committing prematurely to a new stable content kind.

Microsoft.Extensions.AI represents refusals as `ErrorContent(ErrorCode="Refusal")`. Python does not
currently treat refusal output as an error: changing to that model would alter visible-text,
structured-output, and failure-handling behavior beyond preservation of the provider signal.

## Decision Drivers

- Preserve native refusal semantics through streaming and non-streaming paths.
- Keep refusal explanations visible through existing message and response text APIs.
- Round-trip native refusal fields where a transport supports them.
- Preserve history through existing `Content.to_dict()` and `Content.from_dict()` behavior.
- Gather usage of the semantic before adding a stable public discriminator.
- Avoid a parallel content hierarchy or provider-wide parsing abstraction.

## Considered Options

- Keep `type="text"` and record `model_output_kind="refusal"` in `additional_properties`.
- Add a refusal-only boolean marker to text content.
- Add a nested model-output metadata mapping to text content.
- Represent refusals as `ErrorContent`, following Microsoft.Extensions.AI.
- Add a stable `refusal` discriminator to the unified `Content` model.

## Decision Outcome

Keep refusal explanations as ordinary `Content(type="text", text=...)` and add the experimental,
serializable marker:

```python
{"model_output_kind": "refusal"}
```

The flat string value is more general than a refusal-only boolean and cheaper to inspect than a
nested mapping. It is metadata, not a new public API contract: no `ContentType`, constructor,
exported constant, or feature-stage entry is added.

`Message.text`, response/update text, string conversion, and text coalescing remain unchanged.
Structured-output extraction skips marked refusal text so a refusal is not parsed as the requested
response model.

OpenAI Responses, OpenAI Chat Completions, Foundry hosting, Hosting Responses, and DevUI inspect the
marker to reconstruct native refusal fields, content parts, and streaming events. Other providers
and protocols require no refusal-specific behavior because the framework content remains text.

This metadata convention is experimental while usage is gathered. The stable core/OpenAI package
lifecycle is unchanged because no new public API is introduced; beta and alpha hosting/UI packages
retain their package-level lifecycle.

### Consequences

- Serialized refusal content keeps the existing text shape and adds
  `additional_properties.model_output_kind="refusal"`.
- Existing stored refusals remain ordinary text because they carry no reliable migration signal.
- Older runtimes preserve and render the text and serialize the additional property, but do not
  reconstruct native refusal fields until upgraded.
- Native providers can reconstruct their refusal wire representation from durable history without
  relying on non-serializable SDK objects.
- Refusals continue to look like text to middleware and non-native providers.
- A future decision may promote observed usage to `ErrorContent` semantics or a stable discriminator.

### Rejected alternatives

A boolean marker is slightly shorter but creates a refusal-only key that cannot represent another
model-output semantic. A nested mapping reserves more structure than the current requirement needs.
`ErrorContent(ErrorCode="Refusal")` aligns with Microsoft.Extensions.AI but would change Python's
current visible-text and failure semantics. A stable `refusal` discriminator is clearer and may be
appropriate later, but commits the public content model before usage and cross-provider behavior are
understood.
