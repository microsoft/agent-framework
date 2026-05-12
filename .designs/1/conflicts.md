# conflicts.md -- Cross-Dimension Conflict Matrix

## NxN Matrix

Legend: (none) = no conflict, T = tension (trade-off needed), X = direct conflict (resolution required)

|          | D1 (API) | D2 (Data) | D3 (UX) | D4 (Scale) | D5 (Security) | D6 (Integration) |
|----------|----------|-----------|---------|------------|---------------|-------------------|
| D1 (API) | --       | (none)    | (none)  | (none)     | (none)        | T                 |
| D2 (Data)| (none)   | --        | (none)  | (none)     | (none)        | T                 |
| D3 (UX)  | (none)   | (none)    | --      | (none)     | (none)        | (none)            |
| D4 (Scale)| (none)  | (none)    | (none)  | --         | (none)        | (none)            |
| D5 (Sec) | (none)   | (none)    | (none)  | (none)     | --            | (none)            |
| D6 (Int) | T        | T         | (none)  | (none)     | (none)        | --                |

---

## Cell Justifications

### (none) cells

**D1 (API) vs D2 (Data):** No conflict. The API dimension defines the user-facing attribute shapes and generated code structure. The Data dimension defines the internal pipeline models. These are cleanly separated -- attributes are consumed by the pipeline models, with no circular dependency. The attribute shapes (MessageHandlerAttribute, SendsMessageAttribute, YieldsOutputAttribute) are inputs to the analysis pipeline (SemanticAnalyzer reads attribute metadata from ISymbol), and the pipeline models (ExecutorInfo, HandlerInfo) are outputs consumed by SourceBuilder. This is a one-directional dependency with no conflicting requirements.

**D1 (API) vs D3 (UX):** No conflict. The API attributes define what users write; the UX diagnostics validate what they wrote. These are complementary -- the diagnostic messages reference the attribute names and required patterns, but changing one does not require changing the other in a conflicting way. The diagnostics are derived from the validation rules, which are derived from the attribute contract.

**D1 (API) vs D4 (Scale):** No conflict. The attribute-based API is the reason ForAttributeWithMetadataName works so efficiently. A method-level attribute that is discoverable by string name is the ideal input for incremental generator filtering. There is no tension between the API design choice (attributes) and the scalability approach (incremental generation).

**D1 (API) vs D5 (Security):** No conflict. The attribute-based API does not introduce security concerns. Type names in attributes are resolved through Roslyn symbol resolution (not raw string interpolation), so there is no injection vector. The handler accessibility flexibility (C-5: any access level) is secured by partial class semantics, as analyzed in D5.

**D2 (Data) vs D3 (UX):** No conflict. The data models are internal to the generator pipeline and invisible to users. The UX is defined by diagnostics (which are separate from the data models) and the generated code (which is produced by SourceBuilder from the data models). Users never interact with ExecutorInfo, HandlerInfo, etc.

**D2 (Data) vs D4 (Scale):** No conflict. The data model design (records with value equality, ImmutableEquatableArray) was specifically chosen to support incremental generator caching. The scale requirements drove the data model design, so they are aligned rather than in tension.

**D2 (Data) vs D5 (Security):** No conflict. The internal pipeline models do not affect the security posture. They are compile-time-only constructs that do not appear in generated code or diagnostic messages.

**D3 (UX) vs D4 (Scale):** No conflict. The diagnostic messages are lightweight strings generated only when validation fails. They do not impact incremental generation performance. The ForAttributeWithMetadataName predicate runs before any diagnostic generation, so invalid candidates are filtered cheaply.

**D3 (UX) vs D5 (Security):** No conflict. Diagnostic messages contain only method/class names (which are already visible in source code). No sensitive information is leaked through diagnostics.

**D3 (UX) vs D6 (Integration):** No conflict. The UX diagnostics work through standard Roslyn infrastructure that is automatically available when the analyzer is referenced. No additional integration work is needed for diagnostics to appear in IDE or build output.

**D4 (Scale) vs D5 (Security):** No conflict. The incremental generator caching mechanism does not cache or expose sensitive data. Cache keys are derived from value-equality of data models (type names, method names) which are already part of the public source code.

**D4 (Scale) vs D6 (Integration):** No conflict. The incremental generator architecture is compatible with the standard ProjectReference-as-Analyzer integration pattern. The generator runs within the standard Roslyn pipeline without special build system requirements.

**D5 (Security) vs D6 (Integration):** No conflict. The security recommendations (DevelopmentDependency=true, ReferenceOutputAssembly=false) are already part of the integration configuration. These settings ensure the generator does not appear in production deployments.

---

## T (Tension) Cells

### D1 (API) vs D6 (Integration): Plan-vs-Implementation Naming Tension

**Nature:** The plan (source.md) uses names and API shapes that differ from the actual implementation:
- Plan: `YieldsMessageAttribute` -> Actual: `YieldsOutputAttribute`
- Plan: `ConfigureRoutes(RouteBuilder)` -> Actual: `ConfigureProtocol(ProtocolBuilder)`
- Plan: `WFGEN001-006` -> Actual: `MAFGENWF001-007`

**Impact:** AC traceability requires documenting how each AC maps to the actual implementation. Integration tests (AC-16) that reference plan names would not compile.

**Resolution Options:**
1. Rename actual to match plan (REJECTED: reverses commit 0756c457)
2. Add aliases for both names (adds complexity)
3. Document the mapping and accept the deviation (chosen)

**Chosen Resolution:** Option 3 -- Document the mapping in the design-doc traceability table. The actual names are deliberate evolution from the plan, not errors. The plan describes design intent; the implementation refined that intent based on real constraints (naming conflicts per commit 0756c457, unified ProtocolBuilder API per Executor.cs architecture).

**Rationale:** Renaming would break existing consumers. Aliases add complexity for no functional benefit. The deviations are well-documented in codebase-snapshot.md section 4 and have clear git history justification.

### D2 (Data) vs D6 (Integration): Roslyn Version Constraint Tension

**Nature:** The plan (C-2, AC-2) specifies Roslyn 4.8.0+, but the actual implementation uses 4.4.0 (Microsoft.Agents.AI.Workflows.Generators.csproj:49). This creates tension between literal constraint compliance and the project's documented compatibility goals.

**Impact:** If the constraint is taken literally, the implementation is non-compliant. If the constraint intent (use incremental generator APIs) is considered, the implementation is compliant since ForAttributeWithMetadataName is available in 4.4.0.

**Resolution Options:**
1. Upgrade to 4.8.0 (breaks .NET 7 SDK users per .csproj comment)
2. Keep 4.4.0 and document the deviation (chosen)
3. Update the constraint in source.md to say 4.4.0+ (out of scope for design)

**Chosen Resolution:** Option 2 -- Keep 4.4.0 and document the deviation. The .csproj comment explicitly explains the rationale.

**Rationale:** The constraint C-2 appears to have been written based on the assumption that 4.8.0 was the minimum for ForAttributeWithMetadataName, but the API was actually introduced in 4.4.0. The implementation's choice of 4.4.0 maximizes compatibility while still providing the required functionality.

---

## Elevation-Level Conflicts

### Analysis: Do any NEW abstractions or components proposed by one dimension conflict with recommendations from another?

**Finding: No elevation-level conflicts identified.**

All six dimensions recommend preserving the current implementation (Options A1, D1, U1, S1, SEC1, I1). No dimension proposes a new abstraction, component, or architectural change that would conflict with another dimension's recommendation.

The only new components considered were:
- **Code fix providers (D3/U2):** Would be additive, not conflicting. No dimension rejects or contradicts this.
- **SyntaxDetector extraction (D2/D2):** Would be a refactoring, not a new abstraction. No dimension depends on the current inline detection.
- **Integration test project (D6/I3):** Would be additive. No dimension conflicts with this.

Since all recommended options converge on "preserve current implementation," there are no cross-dimension frame conflicts. The design is internally consistent.

### Consistency Check: Recommended Options Across Dimensions

| Dimension | Recommended | Core Principle | Consistent? |
|-----------|-------------|----------------|-------------|
| D1 (API) | A1: Preserve current attributes | Don't reverse deliberate evolution | Yes |
| D2 (Data) | D1: Preserve current models | Implementation is complete and correct | Yes |
| D3 (UX) | U1: Current diagnostics | 7 diagnostics cover all validation rules | Yes |
| D4 (Scale) | S1: Incremental generator | Architecture uses recommended Roslyn patterns | Yes |
| D5 (Security) | SEC1: Current posture | Minimal attack surface, standard model | Yes |
| D6 (Integration) | I1: Current integration | All AC-18 modifications applied | Yes |

All recommendations are mutually consistent. The design surface is mature and does not require cross-cutting changes.
