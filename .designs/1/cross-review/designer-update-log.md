# Designer Update Log — Cross-Review Round 1

**Date**: 2026-05-12
**Reviewer**: rootcause-all (Analyst)
**Review document**: `.designs/1/cross-review/analyst-review-design.md`

## Findings Addressed

### H1: Gap 4 Runtime Failure Mode (HIGH) — INCORPORATED

**Change**: Updated Cross-Perspective Conflicts table (Gap 4 row) to characterize the exact runtime failure: `RouteBuilder.AddHandler<T>` throws `ArgumentException` ("An item with the same key has already been added") when two handlers register the same input type. Updated the MAFGENWF008 resolution to reference this specific exception in the diagnostic message.

**Location**: design-doc.md, Cross-Perspective Conflicts table, Gap 4 row

### H2: Gap 7 Behavioral Equivalence Blocker Clarification (HIGH) — INCORPORATED

**Change**: Updated Six-Sigma Caveats table (Gap 7 row) to explain the specific blocker: the test project has CSharpCompilation infrastructure for generator output verification (structural), but proving behavioral equivalence requires runtime execution of generated code against actual RouteBuilder/ProtocolBuilder instances — this needs an integration test host that compiles, loads, and executes generated assemblies. Structural baseline comparisons (Phase 2) are feasible; full runtime equivalence is not without additional infrastructure.

**Location**: design-doc.md, Six-Sigma Caveats table, Gap 7 row

### H3: Rollback Strategy for Phase 1 Diagnostics (HIGH) — INCORPORATED

**Changes**:
1. Added new risk entry: "New diagnostics (MAFGENWF008, upgraded MAFGENWF006) break consumer CI builds" with mitigation: ship as Warning initially, upgrade to Error in next major version, document in release notes.
2. Updated Phase 1 deliverable #1 to specify MAFGENWF008 ships as Warning (not Error) initially to avoid breaking consumer CI with TreatWarningsAsErrors.

**Location**: design-doc.md, Risk Registry table (new row) and Phase 1 deliverables

## Findings Not Addressed (LOW — no action required per cross-review protocol)

- L1: AC-9 migration impact assessment — noted, no external documentation references the three-method pattern
- L2: Effort estimates beyond "Small" — valid for detailed sprint planning, not required at design level
- L3: Cross-dimension trade-offs section — only 2 tensions exist because dimensions are well-aligned for a validate-existing-work design

## Root Cause Analysis Context

The analyst's `rootcause_analysis.md` covers a different issue (Python FunctionTool sync blocking, #5741). This is the upstream problem being designed for by the soldesign-plan orchestration. The Roslyn source generator design is one component of the broader solution design. No changes to design-doc.md were needed from the rootcause analysis — it validates a Python-side concern orthogonal to the .NET source generator.
