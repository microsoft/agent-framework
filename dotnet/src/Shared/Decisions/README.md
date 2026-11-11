# Decisions

An internal copy of the provider-neutral decision API that is proposed for `Microsoft.Extensions.AI.Abstractions`:
`IDecisionClient`, Binary, Choice, and Score questions and answers, and the typed `DecisionDefinition<TResult>`.
Decision models (Jev, Azure OpenAI Decisions, and others) answer typed questions about a state with calibrated
probabilities, instead of writing text.

The copy lets Agent Framework packages build on the proposed contract before it ships, without exposing it. When
`Microsoft.Extensions.AI` ships the API, this folder is deleted and the same code compiles against the shipped types.

## Source

| Proposal | Pull request | Commit |
|---|---|---|
| Layer 1: provider-neutral decision abstractions | [dotnet/extensions#7795](https://github.com/dotnet/extensions/pull/7795) | `02e54f023bdf3c8c2729353b110c22f5f8593957` |
| Layer 2: decision interoperability (`AsAIFunction`) | [dotnet/extensions#7796](https://github.com/dotnet/extensions/pull/7796) | `e87f1126cf22108fb27f6391c7826fb91c25138e` |

The files are `src/Libraries/Microsoft.Extensions.AI.Abstractions/Decisions/*.cs` at the Layer 2 commit, which contains
Layer 1. The only change is that every top-level type is `internal` instead of `public`. The namespace is still
`Microsoft.Extensions.AI` and the types keep their `[Experimental("MEAI001")]` attributes, so code that uses them looks
the same before and after the API ships. `.editorconfig` keeps the upstream style from failing the build.

Not copied: the upstream tests, the README, and the registration of the decision types in
`AIJsonUtilities.DefaultOptions`. The upstream tests cover the copied code; the tests of the packages that use it
cover their own use.

## Usage

```xml
<PropertyGroup>
  <InjectSharedDecisions>true</InjectSharedDecisions>
  <InjectSharedDiagnosticIds>true</InjectSharedDiagnosticIds>
  <InjectSharedThrow>true</InjectSharedThrow>
</PropertyGroup>
```

The project also needs a package reference to `Microsoft.Extensions.AI.Abstractions`. Code that uses the types
suppresses `MEAI001`, as it will have to once they ship.

Each project that injects this folder compiles its own copy, so the types are distinct per assembly. Do not expose them
in a public API, and do not pass an `IDecisionClient` from one package to another; expose provider-specific types
instead.

## When Microsoft.Extensions.AI ships the API

1. Update `Microsoft.Extensions.AI.Abstractions` in `Directory.Packages.props`. From that version on, the copied types
   conflict with the shipped ones (CS0436), so the next two steps go in the same change.
2. Delete this folder and the `InjectSharedDecisions` item group in `eng/MSBuild/Shared.props`, and remove
   `<InjectSharedDecisions>` from the projects that set it.
3. Fix any difference between this copy and the shipped API, then decide which internal decision clients become
   public.

To follow upstream changes before then, copy the new files over these ones and make the top-level types internal again
(`sed -E 's/^public /internal /'`).
