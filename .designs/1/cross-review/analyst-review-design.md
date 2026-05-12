# Cross-Review: Design Doc (Analyst Perspective)

**Reviewer**: rootcause-all (Analyst)
**Date**: 2026-05-12
**Document Reviewed**: `.designs/1/design-doc.md`

---

## CRITICAL

No critical issues found. The design document is internally consistent, correctly identifies the architecture as sound via elevation analysis, and proposes reasonable incremental improvements to close quality gaps.

---

## HIGH

### H1: Gap 4 (Duplicate Input Types) May Have Broader Impact Than Stated

The design identifies that duplicate handler input types produce runtime exceptions instead of compile-time diagnostics and proposes adding `MAFGENWF008`. However, the root cause chain is incomplete:

- **What happens today**: Two `[MessageHandler]` methods with the same input type on one executor cause a runtime crash
- **Missing analysis**: Does `CombineHandlerMethodResults` deduplicate silently, throw on first conflict, or crash non-deterministically? The behavior under concurrent registration is not characterized
- **Recommendation**: The implementation for MAFGENWF008 should document the exact runtime failure mode it prevents (exception type, stack trace location) so the diagnostic message can reference the specific runtime error users would otherwise encounter

### H2: Behavioral Equivalence Testing (Gap 7) Marked "Partially Feasible" Without Clear Blocking Factor

The design says Gap 7 is "Partially feasible" requiring "in-memory compilation test infrastructure" but the test project already uses `Microsoft.CodeAnalysis.CSharp.CSharpCompilation` for generator tests (implied by 33 existing test methods in `ExecutorRouteGeneratorTests.cs`). If compilation infrastructure already exists, what specifically makes full behavioral equivalence only partially feasible?

- **Recommendation**: Clarify whether the blocker is (a) needing runtime execution of generated code, (b) needing the reflection path to produce comparable output format, or (c) test infrastructure limitations. This affects Phase 2 effort estimation.

### H3: No Rollback Strategy for Phase 1 Diagnostics

Phase 1 adds new compile-time errors (MAFGENWF008, upgraded MAFGENWF006 to Warning). For a published NuGet package:

- New errors break builds that previously succeeded
- New warnings may break builds with TreatWarningsAsErrors

The risk registry covers removal of ReflectingExecutor but not the introduction of new diagnostics that may break existing consumer builds.

- **Recommendation**: Add a risk entry for "new diagnostics break consumer CI" with mitigation: ship new diagnostics as Info initially, upgrade to Warning/Error in next major version. Or document in release notes which diagnostics are new.

---

## LOW

### L1: AC-9 Deviation (ConfigureProtocol vs. Separate Methods) Lacks Migration Impact Assessment

The design correctly notes that generated code uses `ConfigureProtocol` instead of separate `ConfigureRoutes`/`ConfigureSentTypes`/`ConfigureYieldTypes`. The decision table marks this as "Moderate" reversibility but doesn't assess whether any existing documentation, samples, or external guides reference the original three-method pattern. If the plan was published externally before implementation began, consumers may have written code expecting the three-method API.

### L2: Implementation Plan Phases Have No Effort Estimates Beyond "Small"

All three phases are marked "Effort: Small" without LOE breakdown. For planning purposes, distinguishing between "2 hours" and "2 days" matters. The six-sigma gap analysis identifies 13 gaps distributed across 3 phases — even if each gap is small, the aggregate may not be.

### L3: Cross-Dimension Trade-offs Section Is Thin

Only 2 trade-offs documented. Given 6 dimensions were analyzed and 13 gaps identified, the absence of more cross-cutting tensions suggests either (a) the dimensions are well-aligned (possible for a validate-existing-work design) or (b) some tensions were resolved implicitly during analysis without being recorded.

---

## Summary

The design is solid. It correctly validates an existing implementation, identifies meaningful quality gaps, and proposes a reasonable remediation plan. The high-priority findings are about risk completeness and clarity rather than architectural unsoundness. No changes to the core design direction are needed.
