---
status: proposed
contact: christava_microsoft
date: 2026-09-15
deciders: markwallace-microsoft, semenshi
informed: microsoft/agent-framework#1216 participants
---

# Native TypeScript SDK package architecture

## Context and Problem Statement

Agent Framework has Python and .NET implementations but no JavaScript SDK. Issue #1216 requests JavaScript support and invites a community TypeScript contribution. How should a TypeScript implementation enter the repository without coupling Node.js applications to another language runtime or presenting incomplete parity as a released SDK?

## Decision Drivers

- TypeScript applications need native asynchronous and streaming APIs.
- Provider-specific wire formats must remain outside provider-neutral agent code.
- Core function-call behavior must preserve ordered call/result transcripts and exactly-once local execution.
- The implementation must grow incrementally without publishing unsupported compatibility shims.
- Build, test, and dependency management must be isolated from the Python and .NET workspaces.

## Considered Options

- Add a native npm workspace with separate core and provider packages.
- Add one package containing both framework and provider integrations.
- Expose Python or .NET through Node.js process or native bindings.

## Decision Outcome

Chosen option: "Add a native npm workspace with separate core and provider packages", because it matches the repository's provider-neutral architecture while using JavaScript-native promises, async iterables, cancellation, and package tooling.

The initial source preview contains private `@microsoft/agent-framework-core` and `@microsoft/agent-framework-openai` workspaces under `typescript/`. The core package owns messages, response aggregation, agents, middleware, function tools, the local function-calling loop, and in-memory session history. Provider packages depend only on core's public exports and own service request and response translation.

TypeScript tools require explicit JSON Schema because TypeScript annotations are erased at runtime. Host invocation values remain separate from model-generated arguments on the function invocation context. Streaming and non-streaming runs expose equivalent ordered transcripts.

Approvals, durable stores, MCP, workflows, vector stores, hosted tools, telemetry, and additional providers are absent until their complete contracts can be implemented and reviewed. Package publication and release policy require a later decision; the preview workspaces remain private meanwhile.

### Consequences

- Good, because Node.js applications run without a Python or .NET runtime dependency.
- Good, because provider adapters can evolve independently behind a common chat-client contract.
- Good, because deferred capabilities cannot be mistaken for supported partial implementations.
- Bad, because parity arrives over multiple reviewed changes rather than one mechanical translation.
- Bad, because shared behavioral contracts require cross-language conformance tests over time.

## Validation

- Strict TypeScript compilation with `exactOptionalPropertyTypes` and `noUncheckedIndexedAccess`.
- Unit coverage for streaming finalization, middleware ordering, session isolation, cancellation, ordered parallel function calls, limit handling, and provider serialization.
- CI on supported Node.js releases using `npm ci` and `npm run check`.

## Pros and Cons of the Options

### Native workspace with core and provider packages

- Good, because it follows the existing separation between framework contracts and provider transports.
- Good, because it provides idiomatic TypeScript APIs and tree-shakable ESM packages.
- Neutral, because concepts align with Python while language-specific inheritance details do not.
- Bad, because each provider and advanced subsystem needs a native implementation.

### Single package

- Good, because initial installation and repository setup are smaller.
- Bad, because provider dependencies and wire formats leak into the framework core.
- Bad, because future providers increase install size and release coupling.

### Cross-language bindings

- Good, because an existing implementation could be reused.
- Bad, because deployment, debugging, streaming, cancellation, and packaging become cross-runtime concerns.
- Bad, because browser and edge JavaScript environments cannot use the SDK naturally.