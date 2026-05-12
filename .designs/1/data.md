# D2: Data Model

## Dimension Summary

The data model for this source generator encompasses: (1) the intermediate analysis models used within the generator pipeline (ExecutorInfo, HandlerInfo, MethodAnalysisResult, ClassProtocolInfo, AnalysisResult), (2) the attribute data structures consumed from user code, and (3) the project/file structure specified in AC-1 and AC-17.

---

## Internal Generator Models (Pipeline Data)

### Current Model Architecture (Verified from Models/ directory)

The generator uses an incremental pipeline with these data types:

| Model | File | Purpose |
|-------|------|---------|
| MethodAnalysisResult | Models/MethodAnalysisResult.cs | Per-method analysis output from Pipeline 1 |
| ClassProtocolInfo | Models/ClassProtocolInfo.cs | Per-class-attribute output from Pipelines 2/3 |
| AnalysisResult | Models/AnalysisResult.cs | Combined result (ExecutorInfo + Diagnostics) |
| ExecutorInfo | Models/ExecutorInfo.cs | Final executor metadata for code generation |
| HandlerInfo | Models/HandlerInfo.cs | Per-handler metadata (method name, types, signature kind) |
| HandlerSignatureKind | Models/HandlerInfo.cs:8-21 | Enum: VoidSync, VoidAsync, ResultSync, ResultAsync |
| DiagnosticInfo | Models/DiagnosticInfo.cs | Serializable diagnostic for incremental generator caching |
| DiagnosticLocationInfo | Models/DiagnosticLocationInfo.cs | Serializable location for diagnostics |
| ProtocolAttributeKind | Models/ProtocolAttributeKind.cs | Enum: Send vs Yield |
| ImmutableEquatableArray<T> | Models/ImmutableEquatableArray.cs | Value-equality wrapper for ImmutableArray |
| EquatableArray<T> | Models/EquatableArray.cs | Additional equality support |

All models are `record` types (ExecutorInfo.cs:18, HandlerInfo.cs:34) for automatic value equality, which is required by incremental generator caching.

---

## Option D1: Preserve Current Model Architecture (RECOMMENDED)

Keep the existing model structure unchanged. All models listed above exist and are functionally complete.

**Trade-offs:**
- (+) Fully implemented and tested (ExecutorRouteGeneratorTests.cs ~37KB of tests)
- (+) Records provide correct value equality for incremental generator caching
- (+) Clean separation: MethodAnalysisResult (per-method) -> CombineHandlerMethodResults (per-class) -> ExecutorInfo (for generation)
- (+) ImmutableEquatableArray solves the known Roslyn incremental generator caching problem with ImmutableArray
- (-) AC-1 specifies a `SyntaxDetector.cs` file that does not exist separately; detection is inline in ExecutorRouteGenerator.cs via `ForAttributeWithMetadataName`

**Reversibility:** Easy -- models are internal to the generator.

**Constraint compliance:**
- C-1 (netstandard2.0): All models use only netstandard2.0-compatible types. Records are enabled via `InjectIsExternalInitOnLegacy` in the .csproj.
- C-2 (Roslyn 4.8+): Note -- actual .csproj references Roslyn 4.4.0 (Microsoft.Agents.AI.Workflows.Generators.csproj:49), not 4.8.0+. Roslyn 4.4.0 is the minimum version supporting `ForAttributeWithMetadataName`. The constraint C-2 says "4.8.0+" but the implementation deliberately chose 4.4.0 for broader SDK compatibility (see comment in .csproj lines 45-48).

**Dependencies produced:** ExecutorInfo and HandlerInfo consumed by D1 (API -- SourceBuilder), D6 (integration -- code generation).
**Dependencies required:** Attribute shapes from D1 (API).

**Risks:**
- Severity: Medium. C-2 says "Reference Microsoft.CodeAnalysis.CSharp 4.8.0+" but actual uses 4.4.0.
- Mitigation: The 4.4.0 choice is deliberate and documented in the .csproj comment. The `ForAttributeWithMetadataName` API used throughout the generator was introduced in 4.4.0. Using 4.8.0 would exclude users on older .NET SDKs. This is a conscious deviation from the plan for compatibility reasons.

---

## Option D2: Extract SyntaxDetector as Separate File (Per AC-1)

Create a `SyntaxDetector.cs` file that wraps the inline `ForAttributeWithMetadataName` predicates currently in ExecutorRouteGenerator.cs:33-53.

**Trade-offs:**
- (+) Matches AC-1 file structure exactly
- (+) Separates concerns (detection vs analysis vs generation)
- (-) The predicates are trivially simple (`node is MethodDeclarationSyntax`, `node is ClassDeclarationSyntax`) -- extracting them adds indirection without value
- (-) Roslyn's `ForAttributeWithMetadataName` already IS the syntax detection; wrapping it adds no abstraction benefit
- (-) AC-15 specifies `SyntaxDetectorTests.cs` which would need test targets

**Reversibility:** Easy.

**Constraint compliance:** All constraints met.

**Dependencies produced:** SyntaxDetector class consumed by ExecutorRouteGenerator.
**Dependencies required:** None.

**Risks:**
- Severity: Low. Thin wrapper adds no meaningful testable surface.
- Mitigation: If extracted, tests would verify predicate logic (trivial).

---

## Option D3: Add Explicit Model for AC-10 Inheritance Scenarios

Currently, inheritance handling is encoded in the `BaseHasConfigureProtocol` boolean flag on ExecutorInfo (ExecutorInfo.cs:25). AC-10 describes three scenarios:
1. Directly extends Executor -> No base call
2. Extends executor with [MessageHandler] methods -> base call
3. Extends executor with manual ConfigureRoutes -> base call

Option: Replace the single boolean with a richer enum/model capturing the exact inheritance scenario.

**Trade-offs:**
- (+) More explicit about inheritance intent
- (+) Easier to extend if new inheritance scenarios arise
- (-) The boolean already correctly captures the needed decision (call base or not)
- (-) SemanticAnalyzer.cs:424-448 (`BaseHasConfigureProtocol`) correctly walks the chain and detects both scenarios 2 and 3
- (-) Adds complexity for a single code-generation decision point

**Reversibility:** Easy -- internal to generator.

**Constraint compliance:** All constraints met.

**Dependencies produced:** Richer inheritance model consumed by SourceBuilder.
**Dependencies required:** None.

**Risks:**
- Severity: Low.
- Mitigation: N/A.

---

## Option D4: Upgrade Roslyn Reference to 4.8.0+ Per C-2

Change `Microsoft.CodeAnalysis.CSharp` from `4.4.0` to `4.8.0` to match constraint C-2 literally.

**REJECTED: violates C-2 intent (broader compatibility)**

While C-2 says "Reference Microsoft.CodeAnalysis.CSharp 4.8.0+", the .csproj comment (lines 45-48) documents a deliberate choice: "Use Roslyn 4.4.0 - minimum version for ForAttributeWithMetadataName API. Corresponds to .NET 7 SDK / VS 2022 17.4+. Higher versions would require newer SDKs, breaking users on older versions." Upgrading to 4.8.0 would break users on .NET 7 SDK, which contradicts the project's compatibility goals.

**Trade-offs:**
- (+) Matches C-2 verbatim
- (-) Breaks .NET 7 SDK users
- (-) No API from 4.8.0 is actually used by the generator
- (-) Contradicts the documented rationale in the .csproj

**Reversibility:** Easy.

---

## Project Structure (AC-1, AC-17)

### Actual vs Plan File Mapping

| Plan Path (AC-1/AC-17) | Actual Path | Status |
|------------------------|-------------|--------|
| ExecutorRouteGenerator.cs | ExecutorRouteGenerator.cs | EXISTS, matches |
| Models/ExecutorInfo.cs | Models/ExecutorInfo.cs | EXISTS, matches |
| Models/HandlerInfo.cs | Models/HandlerInfo.cs | EXISTS, matches |
| Analysis/SyntaxDetector.cs | (inline in ExecutorRouteGenerator.cs) | DIFFERENT -- detection via ForAttributeWithMetadataName |
| Analysis/SemanticAnalyzer.cs | Analysis/SemanticAnalyzer.cs | EXISTS, matches |
| Generation/SourceBuilder.cs | Generation/SourceBuilder.cs | EXISTS, matches |
| Diagnostics/DiagnosticDescriptors.cs | Diagnostics/DiagnosticDescriptors.cs | EXISTS, matches |
| (not in plan) | Models/AnalysisResult.cs | EXTRA -- needed for pipeline |
| (not in plan) | Models/ClassProtocolInfo.cs | EXTRA -- needed for pipeline |
| (not in plan) | Models/MethodAnalysisResult.cs | EXTRA -- needed for pipeline |
| (not in plan) | Models/DiagnosticInfo.cs | EXTRA -- needed for caching |
| (not in plan) | Models/DiagnosticLocationInfo.cs | EXTRA -- needed for caching |
| (not in plan) | Models/ProtocolAttributeKind.cs | EXTRA -- Send vs Yield enum |
| (not in plan) | Models/ImmutableEquatableArray.cs | EXTRA -- equality for caching |
| (not in plan) | Models/EquatableArray.cs | EXTRA -- equality for caching |
| (not in plan) | Directory.Build.targets | EXTRA -- build plumbing |
| (not in plan) | SkipIncompatibleBuild.targets | EXTRA -- build plumbing |

The additional files are necessary for a correct incremental generator implementation (caching requires value equality on all pipeline data). The plan underestimated the model count.

---

## Summary

**Recommended option: D1** -- Preserve current model architecture. The implementation is complete, tested, and correctly handles incremental generator caching requirements. The SyntaxDetector.cs absence is a simplification (not a gap), and the Roslyn 4.4.0 choice is a deliberate compatibility decision.
