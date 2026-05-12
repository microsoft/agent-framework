# D3: User Experience

## Dimension Summary

User experience for a source generator is mediated through: (1) the attribute-based declaration API that developers write, (2) compile-time diagnostics that guide correct usage, (3) the migration path from `ReflectingExecutor<T>` to the source-generated approach, and (4) IDE integration (IntelliSense, error squiggles, generated code visibility).

---

## Option U1: Current UX with Comprehensive Diagnostics (RECOMMENDED)

The existing implementation provides a full diagnostic suite (7 diagnostics, MAFGENWF001-007) covering all validation scenarios. Users get immediate feedback in their IDE when handler signatures are wrong, classes are not partial, or classes do not derive from Executor.

**Happy path workflow:**
1. User creates a `partial class` extending `Executor`
2. User adds `[MessageHandler]` to handler methods
3. Source generator runs automatically during build/IDE typing
4. Generated `ConfigureProtocol` override appears in IDE (can be inspected via "Go to Generated Files")
5. If handler has wrong signature -> red squiggle with MAFGENWF001/002/005/007
6. If class not partial -> red squiggle with MAFGENWF003
7. If class not an Executor -> warning squiggle with MAFGENWF004

**Failure path UX:**
- MAFGENWF001 (Error): "Method 'X' marked with [MessageHandler] must have IWorkflowContext as the second parameter" -- actionable, tells user exactly what parameter to add
- MAFGENWF002 (Error): "Method 'X' marked with [MessageHandler] must return void, ValueTask, or ValueTask<T>" -- actionable, lists valid return types
- MAFGENWF003 (Error): "Class 'X' contains [MessageHandler] methods but is not declared as partial" -- actionable, add `partial`
- MAFGENWF004 (Warning): "Method 'X' is marked with [MessageHandler] but class 'Y' does not derive from Executor" -- warning because the attribute can exist on non-executors without harm
- MAFGENWF005 (Error): "Method 'X' marked with [MessageHandler] must have at least 2 parameters (message and IWorkflowContext)" -- actionable
- MAFGENWF006 (Info): "Class 'X' already defines ConfigureProtocol; [MessageHandler] methods will be ignored" -- informational, no action needed
- MAFGENWF007 (Error): "Method 'X' marked with [MessageHandler] cannot be static" -- actionable, remove `static`

**Trade-offs:**
- (+) Complete diagnostic coverage for all AC-7 validation rules plus the additional static check
- (+) Error messages are actionable and include the offending method/class name
- (+) MAFGENWF006 gracefully handles the coexistence scenario (manual + attributed)
- (+) Works with any handler accessibility level (private, protected, internal, public) per C-5
- (-) No code fix providers (IDE quick-fixes like "make class partial") -- users must apply fixes manually

**Reversibility:** Easy.

**Constraint compliance:**
- C-4 (clean break): The `[Obsolete]` on `ReflectingExecutor<T>` (ReflectingExecutor.cs:21-22) warns users during migration
- C-5 (any accessibility): Verified -- SemanticAnalyzer does not check accessibility modifiers
- C-6 (partial required): MAFGENWF003 enforces this

**Dependencies produced:** Diagnostic message text consumed by D5 (security -- information leakage review).
**Dependencies required:** Attribute shapes from D1 (API), validation rules from D2 (data model).

**Risks:**
- Severity: Low. No code fix providers means slightly higher friction during migration.
- Mitigation: The `[Obsolete]` message on ReflectingExecutor already points users to the migration path.

---

## Option U2: Add Roslyn Code Fix Providers

Implement `CodeFixProvider` classes for the most common diagnostics:
- MAFGENWF003: Auto-add `partial` modifier
- MAFGENWF005: Auto-add `IWorkflowContext` parameter stub
- MAFGENWF007: Auto-remove `static` modifier

**Trade-offs:**
- (+) One-click fixes in IDE reduce migration friction
- (+) Standard Roslyn practice for analyzer+generator packages
- (-) Code fix providers are a separate assembly that must also target netstandard2.0
- (-) Increases scope: new project, new tests, packaging complexity
- (-) Not in any AC or constraint -- pure scope expansion

**Reversibility:** Easy -- code fixes are additive.

**Constraint compliance:** C-3 applies (must package as analyzer).

**Dependencies produced:** Code fix assembly consumed by D6 (integration -- NuGet packaging).
**Dependencies required:** Diagnostic descriptors from D1 (API).

**Risks:**
- Severity: Low. Adds scope not in the plan.
- Mitigation: Could be a follow-up iteration.

---

## Option U3: Migration Guide Documentation

Create a migration guide document that walks users through converting `ReflectingExecutor<T>` subclasses to source-generated executors.

**Trade-offs:**
- (+) Reduces confusion during the clean-break migration (C-4)
- (+) The `[Obsolete]` message on ReflectingExecutor.cs:21-22 says "See migration guide" -- so a guide is implicitly promised
- (-) Documentation is out of scope for this design (no AC covers it)
- (-) Docs can become stale

**Reversibility:** Easy.

**Constraint compliance:** All constraints met.

**Dependencies produced:** Documentation consumed by D6 (integration).
**Dependencies required:** Final attribute API from D1.

**Risks:**
- Severity: Low.

---

## Option U4: Add Source Generator Telemetry/Logging

Add diagnostic logging to the source generator to help debug issues when generation silently fails or produces unexpected output.

**REJECTED: violates C-1 (netstandard2.0 restrictions)**

Source generators running in the Roslyn compiler host have very limited access to logging/telemetry infrastructure. The netstandard2.0 constraint (C-1) and the analyzer sandbox further restrict available APIs. Roslyn's recommended approach is diagnostics (which the generator already uses via MAFGENWF001-007).

**Trade-offs:**
- (+) Would help debug complex inheritance chains
- (-) No reliable logging channel available in analyzer context
- (-) Adds dependency on logging framework incompatible with analyzer hosting

**Reversibility:** Moderate.

---

## Summary

**Recommended option: U1** -- The current UX with 7 diagnostics provides comprehensive coverage. Code fix providers (U2) and migration guides (U3) are valuable follow-ups but are out of scope for the current design.
