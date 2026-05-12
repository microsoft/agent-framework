# D1: API & Interface Design

## Dimension Summary

The source generator system exposes three user-facing APIs: (1) attribute declarations on executor classes/methods, (2) the generated code interface (ConfigureProtocol override), and (3) diagnostic messages surfaced in the IDE/build. The design challenge is reconciling the plan's specified attribute shapes with the actual evolved implementation.

## Key Discrepancies from Source

The plan (source.md AC-3 through AC-5) specifies attribute signatures that already exist in the codebase with minor variations:
- Plan says `YieldsMessageAttribute` -> actual is `YieldsOutputAttribute` (codebase-snapshot.md section 3)
- Plan says `AttributeTargets.Class` only for SendsMessage/YieldsOutput -> actual allows `Class | Method` (SendsMessageAttribute.cs:32, YieldsOutputAttribute.cs:32)
- Plan says `ConfigureRoutes(RouteBuilder)` -> actual is `ConfigureProtocol(ProtocolBuilder)` (Executor.cs:216, SourceBuilder.cs:72)
- Plan says `WFGEN001-006` -> actual is `MAFGENWF001-007` (DiagnosticDescriptors.cs)

---

## Option A1: Preserve Current Attribute Names and Signatures (RECOMMENDED)

Keep the existing attribute names (`YieldsOutputAttribute`, `SendsMessageAttribute` with `Class | Method` targets) and the evolved `ConfigureProtocol(ProtocolBuilder)` pattern.

**Trade-offs:**
- (+) Zero breaking changes for existing consumers
- (+) The `Class | Method` target is strictly more capable than `Class` only
- (+) `YieldsOutput` is more semantically precise than `YieldsMessage` (outputs are yielded, messages are sent)
- (+) `ConfigureProtocol` unifies route + type registration into a single fluent builder
- (-) Source.md AC-5 says "YieldsMessageAttribute" verbatim; the actual name differs
- (-) Source.md AC-9 describes separate `ConfigureSentTypes()`/`ConfigureYieldTypes()` methods; actual unifies these

**Reversibility:** Difficult -- renaming attributes or splitting ConfigureProtocol would break all downstream consumers.

**Constraint compliance:**
- C-4 (clean break): Compliant. Users inherit from `Executor`, not `ReflectingExecutor<T>`.
- C-5 (handler accessibility): Compliant. SemanticAnalyzer.cs:462 (`AnalyzeHandler`) does not check accessibility.
- C-6 (partial modifier): Compliant. SemanticAnalyzer.cs:367-380 (`IsPartialClass`) checks for `partial`.

**Dependencies produced:** Attribute shapes consumed by D2 (data model), D6 (integration).
**Dependencies required:** None.

**Risks:**
- Severity: Low. Risk that plan-vs-actual naming discrepancy causes confusion during review.
- Mitigation: Document discrepancies in design-doc.md traceability table.

---

## Option A2: Rename to Match Plan Exactly (YieldsMessageAttribute, Split ConfigureRoutes/ConfigureSentTypes/ConfigureYieldTypes)

Rename `YieldsOutputAttribute` to `YieldsMessageAttribute`, restrict SendsMessage/YieldsMessage to `AttributeTargets.Class` only, and split the generated code back into three separate override methods.

**REJECTED: reverses [commit 0756c457] (.NET: [BREAKING] Update type names and source generator to reduce conflicts)**

The commit `0756c457` was a deliberate breaking change that renamed types and restructured the generated code to avoid conflicts. Reversing this would undo a deliberate architectural decision documented in the git history.

Additionally, reverses the evolution to `ConfigureProtocol(ProtocolBuilder)` which is the actual abstract method on Executor.cs:216.

**Trade-offs:**
- (+) Matches source.md AC-5, AC-9 verbatim
- (-) Breaks all existing users of `YieldsOutputAttribute`
- (-) Reintroduces the naming conflicts that commit `0756c457` was designed to fix
- (-) `ConfigureRoutes`/`ConfigureSentTypes`/`ConfigureYieldTypes` as separate overrides does not exist on the actual `Executor` base class

**Reversibility:** Difficult.

---

## Option A3: Add Type Aliases for Plan Names While Keeping Actual Names

Add `YieldsMessageAttribute` as a type-forwarding alias to `YieldsOutputAttribute`, allowing both names. Keep the evolved `ConfigureProtocol` pattern.

**Trade-offs:**
- (+) Satisfies AC-5 literally (a type named `YieldsMessageAttribute` exists)
- (+) No breaking change
- (-) Two names for the same concept increases cognitive load
- (-) Source generator must detect both attribute names, increasing complexity
- (-) Aliases create long-term maintenance burden

**Reversibility:** Easy -- alias can be removed later.

**Constraint compliance:** All constraints met.

**Dependencies produced:** Attribute detection changes needed in D6 (integration -- generator pipeline).
**Dependencies required:** None.

**Risks:**
- Severity: Medium. Two names for one concept will confuse developers.
- Mitigation: Deprecate the alias immediately with `[Obsolete]`.

---

## Option A4: Document Divergence, No Code Changes

Accept that the plan describes a prior design intent, and the implementation has evolved. Document the mapping between plan names and actual names in the design-doc traceability table. No code changes.

**Trade-offs:**
- (+) Zero risk, zero code changes
- (+) Honest about the evolutionary path
- (-) AC-5 says "YieldsMessageAttribute" which technically does not exist by that exact name
- (-) AC-9 describes a code structure that differs from actual generated output

**Reversibility:** Easy.

**Constraint compliance:** All constraints met.

**Dependencies produced:** Documentation artifacts for D6 (integration).
**Dependencies required:** None.

**Risks:**
- Severity: Low.
- Mitigation: Traceability table maps each AC to actual implementation.

---

## Diagnostic IDs (AC-11)

### Current State (Verified from DiagnosticDescriptors.cs)

| Plan ID | Actual ID | Severity | Condition | Match? |
|---------|-----------|----------|-----------|--------|
| WFGEN001 | MAFGENWF001 | Error | Handler missing IWorkflowContext parameter | Functional match |
| WFGEN002 | MAFGENWF002 | Error | Handler has invalid return type | Functional match |
| WFGEN003 | MAFGENWF003 | Error | Executor with [MessageHandler] must be partial | Functional match |
| WFGEN004 | MAFGENWF004 | Warning | [MessageHandler] on non-Executor class | Functional match |
| WFGEN005 | MAFGENWF005 | Error | Handler has fewer than 2 parameters | Functional match |
| WFGEN006 | MAFGENWF006 | Info | ConfigureProtocol already defined (plan says ConfigureRoutes) | Functional match |
| (none) | MAFGENWF007 | Error | Handler cannot be static | Extra diagnostic |

The MAFGENWF prefix follows Microsoft Agent Framework naming convention. The additional MAFGENWF007 (static handler check) is a correctness improvement over the plan.

### Recommendation

Preserve the MAFGENWF IDs. The plan's WFGEN IDs were never implemented; changing to them would break any tooling or documentation referencing the actual IDs.

---

## Handler Signature Mapping (AC-8)

Verified in SemanticAnalyzer.cs:539-568 (`GetSignatureKind`) and SourceBuilder.cs:178-189 (`AppendHandlerGenericArgs`):

| Method Signature | Generated Call | Verified? |
|-----------------|----------------|-----------|
| void Handler(T, IWorkflowContext) | AddHandler<T>(this.Handler) | Yes -- VoidSync in HandlerInfo.cs:10, HasOutput=false |
| void Handler(T, IWorkflowContext, CT) | AddHandler<T>(this.Handler) | Yes -- VoidSync with hasCancellationToken=true |
| ValueTask Handler(T, IWorkflowContext) | AddHandler<T>(this.Handler) | Yes -- VoidAsync, HasOutput=false |
| ValueTask Handler(T, IWorkflowContext, CT) | AddHandler<T>(this.Handler) | Yes -- VoidAsync with hasCancellationToken=true |
| TResult Handler(T, IWorkflowContext) | AddHandler<T, TResult>(this.Handler) | Yes -- ResultSync, HasOutput=true |
| ValueTask<TResult> Handler(T, IWorkflowContext, CT) | AddHandler<T, TResult>(this.Handler) | Yes -- ResultAsync, HasOutput=true |

Note: AC-8 omits `TResult Handler(T, IWorkflowContext, CT)` (sync with CT) and `ValueTask<TResult> Handler(T, IWorkflowContext)` (async result without CT), but the implementation handles all 8 combinations per RouteBuilder's overloads (RouteBuilder.cs:51-89 and overloads).

---

## Summary

**Recommended option: A1** -- Preserve current attribute names and signatures. The implementation has evolved beyond the plan in well-reasoned ways (commit `0756c457`, unified `ConfigureProtocol`), and reverting would introduce breakage with no functional benefit.
