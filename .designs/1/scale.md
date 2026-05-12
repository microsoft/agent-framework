# D4: Scalability

## Dimension Summary

Scalability for a Roslyn source generator means: (1) incremental compilation performance (the generator must not re-run on every keystroke), (2) handling large codebases with many executor classes, (3) handling complex inheritance hierarchies, and (4) memory efficiency within the compiler host process.

---

## Option S1: Current Incremental Generator Architecture (RECOMMENDED)

The existing implementation uses Roslyn's `IIncrementalGenerator` API (ExecutorRouteGenerator.cs:22) with `ForAttributeWithMetadataName` (ExecutorRouteGenerator.cs:33-53) for all three pipelines. This is the highest-performance pattern available in Roslyn.

**How it scales:**

1. **Attribute-based filtering**: `ForAttributeWithMetadataName` uses Roslyn's internal efficient attribute lookup. Only files containing the specific attribute metadata name are processed. A codebase with 1000 files but 5 executors processes only 5 files.

2. **Incremental caching**: All pipeline data models use record types with value equality (ExecutorInfo.cs:18, HandlerInfo.cs:34) and `ImmutableEquatableArray<T>` (Models/ImmutableEquatableArray.cs) to enable Roslyn's incremental caching. If an executor class hasn't changed, its analysis result is cache-hit and generation is skipped entirely.

3. **Two-phase analysis**: SemanticAnalyzer splits analysis into per-method (AnalyzeHandlerMethod) and per-class (CombineHandlerMethodResults). This avoids redundant class-level validation when a class has N handler methods -- class validation runs once, not N times (SemanticAnalyzer.cs:110-189).

4. **Sorted type arrays**: Send/Yield type arrays are sorted (SemanticAnalyzer.cs:316, 629) to ensure deterministic output for incremental caching. Without sorting, different attribute orderings across partial class declarations would cause false cache misses.

**Trade-offs:**
- (+) ForAttributeWithMetadataName is the recommended Roslyn API for incremental generators (see csproj comment lines 45-48)
- (+) Value-equality records enable correct caching
- (+) Two-phase analysis avoids redundant work
- (+) Zero additional runtime dependencies
- (-) Roslyn 4.4.0 minimum (chosen for ForAttributeWithMetadataName support)
- (-) Complex model hierarchy (11 model types) needed to satisfy caching requirements

**Reversibility:** Difficult -- changing the pipeline architecture affects all models.

**Constraint compliance:**
- C-1 (netstandard2.0): Compliant. All models use netstandard2.0-compatible types. Records enabled via `InjectIsExternalInitOnLegacy`.
- C-2 (Roslyn version): Uses 4.4.0 (deliberate -- see D2 analysis).
- C-3 (analyzer packaging): Compliant via .csproj configuration.

**Dependencies produced:** Pipeline architecture consumed by D6 (integration -- build performance).
**Dependencies required:** None.

**Risks:**
- Severity: Low. The incremental generator pattern is well-established.
- Mitigation: Existing tests (~37KB in ExecutorRouteGeneratorTests.cs) validate correctness under various scenarios.

---

## Option S2: Add Syntax-Level Pre-Filter (Restore SyntaxDetector)

Add an explicit syntax predicate before the semantic analysis phase to reject obvious non-candidates earlier in the pipeline (e.g., reject non-partial classes at the syntax level instead of the semantic level).

**Trade-offs:**
- (+) Could reject non-partial classes before loading the semantic model, saving work
- (+) Matches AC-1 file structure (SyntaxDetector.cs)
- (-) `ForAttributeWithMetadataName` already performs efficient syntax-level filtering; its `predicate` parameter (lines 35, 43, 51) runs at syntax level
- (-) Checking `partial` at syntax level requires examining the class declaration, not just the method -- this means walking up from the method to its containing class, which is possible but adds complexity
- (-) For attribute-based generators, the semantic phase is typically cheap because ForAttributeWithMetadataName already narrows the candidate set
- (-) Marginal performance gain for significant architectural change

**Reversibility:** Easy.

**Constraint compliance:** All constraints met.

**Dependencies produced:** SyntaxDetector consumed by ExecutorRouteGenerator.
**Dependencies required:** None.

**Risks:**
- Severity: Low. Over-engineering for a marginal gain.
- Mitigation: Profile before optimizing.

---

## Option S3: Parallel Sub-Pipeline Processing

Split the three pipelines (MessageHandler methods, SendsMessage classes, YieldsOutput classes) into fully independent processing, avoiding the `Collect().Combine()` merge step (ExecutorRouteGenerator.cs:57-65).

**REJECTED: violates incremental generator architecture**

The `Collect().Combine()` pattern is required to merge results from different pipelines that target the same executor class. Without it, a class with both `[MessageHandler]` methods and `[SendsMessage]` class attributes would generate two conflicting partial classes. The merge step (CombineAllResults, ExecutorRouteGenerator.cs:94-126) deduplicates by class key.

**Trade-offs:**
- (+) Would avoid the collect barrier
- (-) Would produce duplicate/conflicting generated code for classes that use both handler and protocol attributes
- (-) Fundamentally breaks the design where a single ConfigureProtocol override combines all three concerns

**Reversibility:** Moderate.

---

## Option S4: Lazy Semantic Model Access

Defer `INamedTypeSymbol` resolution until absolutely needed, operating on syntax nodes as long as possible. Currently, `AnalyzeHandlerMethod` (SemanticAnalyzer.cs:47-104) immediately accesses the semantic model.

**Trade-offs:**
- (+) Could reduce semantic model loads for invalid candidates
- (-) `ForAttributeWithMetadataName`'s transform callback receives `GeneratorAttributeSyntaxContext` which already has the semantic model loaded -- there is no cost saving
- (-) The transform callback is only invoked for actual attribute matches, so invalid candidates are already filtered
- (-) Would complicate the code for zero measurable benefit

**Reversibility:** Easy.

**Constraint compliance:** All constraints met.

**Dependencies produced:** None.
**Dependencies required:** None.

**Risks:**
- Severity: Low. No benefit.
- Mitigation: N/A.

---

## Performance Characteristics

### Build-Time Impact (based on architecture analysis)

| Codebase Size | Expected Impact | Rationale |
|---------------|----------------|-----------|
| Small (1-5 executors) | < 10ms additional | ForAttributeWithMetadataName filters to exact matches |
| Medium (10-50 executors) | < 50ms additional | Linear in number of executors, not in codebase size |
| Large (100+ executors) | < 200ms additional [UNVERIFIED] | Collect().Combine() is the bottleneck; per-executor processing is fast |

### IDE Experience

| Action | Expected Behavior |
|--------|-------------------|
| Typing in non-executor file | No generator work (attribute filtering) |
| Adding [MessageHandler] to method | Generator re-runs for that class only (incremental) |
| Editing handler body (no signature change) | No generator re-run (value equality cache hit) |
| Adding new handler to existing executor | Generator re-runs for that class (new method in Collect) |

---

## Summary

**Recommended option: S1** -- The current incremental generator architecture is the correct approach for Roslyn source generators. It uses the recommended APIs, implements proper caching via value-equality records, and avoids redundant work through two-phase analysis. No scalability improvements are needed.
