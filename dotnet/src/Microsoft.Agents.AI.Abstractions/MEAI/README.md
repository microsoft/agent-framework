# MEAI

A copy of the provider-neutral decision API that is proposed for `Microsoft.Extensions.AI.Abstractions`:
`IDecisionClient`, Binary, Choice, and Score questions and answers, the typed `DecisionDefinition<TResult>`, and
`DecisionDefinition<TResult>.AsAIFunction`. Decision models (Jev, Azure OpenAI Decisions, and others) answer typed
questions about a state with probabilities, instead of writing text.

The types are public, in the `Microsoft.Extensions.AI` namespace, and marked `[Experimental("MEAI001")]`, exactly as
proposed, although they ship in this Agent Framework package. Code written against them today, such as provider
clients and samples, is the code that will compile against the shipped API. This follows how Agent Framework shipped
proposed MEAI types before they were released (#279, #426), and deleted them once MEAI shipped them (#427, #676).

## Source

| Proposal | Pull request | Commit |
|---|---|---|
| Layer 1: provider-neutral decision abstractions | [dotnet/extensions#7795](https://github.com/dotnet/extensions/pull/7795) | `02e54f023bdf3c8c2729353b110c22f5f8593957` |
| Layer 2: decision interoperability (`AsAIFunction`) | [dotnet/extensions#7796](https://github.com/dotnet/extensions/pull/7796) | `e87f1126cf22108fb27f6391c7826fb91c25138e` |

The files are `src/Libraries/Microsoft.Extensions.AI.Abstractions/Decisions/*.cs` at the Layer 2 commit, which contains
Layer 1, without changes. `.editorconfig` keeps the upstream style and API shape from failing the build. The package
injects `src/Shared/DiagnosticIds` and `src/Shared/Throw`, which provide the helpers the upstream code uses, and the
polyfills that the upstream code relies on for .NET Standard 2.0 and .NET Framework.

Not copied: the upstream tests, the README, and the registration of the decision types in
`AIJsonUtilities.DefaultOptions`. Serializing the decision types therefore uses reflection-based metadata.

## Placement

The copy lives where MEAI places the API: everything is in `Microsoft.Extensions.AI.Abstractions` upstream, so it is in
`Microsoft.Agents.AI.Abstractions` here, which every provider package depends on. Only this package may carry the copy,
because a second package with the same public types would make them ambiguous (CS0433) for an application that
references both.

The API is still in review, and the review on #7795 asks, among other things, to align `DecisionResponse` with
`ChatResponse` and to move the typed layer (`DecisionDefinition<TResult>`, `DecisionResponse<TResult>`, and the typed
extensions) to `Microsoft.Extensions.AI`. When upstream changes, copy the new files over these ones and update the
public API files. If the typed layer moves to `Microsoft.Extensions.AI`, move its copy to `Microsoft.Agents.AI`. Each
re-sync can break code that uses the types, which their `MEAI001` diagnostic allows.

## When Microsoft.Extensions.AI ships the API

1. Update `Microsoft.Extensions.AI.Abstractions` in `Directory.Packages.props`. From that version on, the copied types
   conflict with the shipped ones, so the next steps go in the same change and the same release.
2. Delete this folder and its entries in `PublicAPI/*/PublicAPI.Unshipped.txt` (or `PublicAPI.Shipped.txt`, once a
   release has shipped them).
3. Add `[assembly: TypeForwardedTo(typeof(...))]` for each public type, so applications compiled against this package
   keep loading the types from `Microsoft.Extensions.AI.Abstractions`. Suppress any package validation difference
   between this copy and the shipped shape in `CompatibilitySuppressions.xml`.
4. Fix any difference between this copy and the shipped API in the packages that use it, such as
   `Microsoft.Agents.AI.TypeSafe` and the samples.
