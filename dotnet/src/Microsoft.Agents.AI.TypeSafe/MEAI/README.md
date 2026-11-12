# MEAI

A copy of the provider-neutral decision API that is proposed for `Microsoft.Extensions.AI.Abstractions`:
`IDecisionClient`, Binary, Choice, and Score questions and answers, the typed `DecisionDefinition<TResult>`, and
`DecisionDefinition<TResult>.AsAIFunction`. Decision models (Jev, Azure OpenAI Decisions, and others) answer typed
questions about a state with probabilities, instead of writing text.

The types are public, in the `Microsoft.Extensions.AI` namespace, and marked `[Experimental("MEAI001")]`, exactly as
proposed. Code written against them today, such as `JevDecisionClient` and the samples, is the code that will compile
against the shipped API. This follows how Agent Framework shipped proposed MEAI types before they were released
(#279, #426), and deleted them once MEAI shipped them (#427, #676).

## Source

| Proposal | Pull request | Commit |
|---|---|---|
| Layer 1: provider-neutral decision abstractions | [dotnet/extensions#7795](https://github.com/dotnet/extensions/pull/7795) | `02e54f023bdf3c8c2729353b110c22f5f8593957` |
| Layer 2: decision interoperability (`AsAIFunction`) | [dotnet/extensions#7796](https://github.com/dotnet/extensions/pull/7796) | `e87f1126cf22108fb27f6391c7826fb91c25138e` |

The files are `src/Libraries/Microsoft.Extensions.AI.Abstractions/Decisions/*.cs` at the Layer 2 commit, which contains
Layer 1, without changes. `.editorconfig` keeps the upstream style from failing the build, and the project injects
`src/Shared/DiagnosticIds` and `src/Shared/Throw`, which provide the helpers the upstream code uses.

Not copied: the upstream tests, the README, and the registration of the decision types in
`AIJsonUtilities.DefaultOptions`. Serializing the decision types therefore uses reflection-based metadata.

The API is still in review. In particular, the API review on #7795 asks to align `DecisionResponse` with
`ChatResponse` (`ModelId` and `ResponseId` instead of `DecisionProvenance`, settable properties), and the shape may
change before it ships.

## Only one package carries the copy

The types live in this package so that it can expose them. A second package that defined the same public types would
make them ambiguous (CS0433) for an application that references both. Before another package, such as an Azure OpenAI
Decisions provider, needs the API, move this folder to a package that both depend on.

## When Microsoft.Extensions.AI ships the API

1. Update `Microsoft.Extensions.AI.Abstractions` in `Directory.Packages.props`. From that version on, the copied types
   conflict with the shipped ones, so the next steps go in the same change.
2. Delete this folder.
3. Fix any difference between this copy and the shipped API in `JevDecisionClient`, the shared decision chat engine
   (`src/Shared/DecisionChat`), and the samples.

To follow upstream changes before then, copy the new upstream files over these ones.
