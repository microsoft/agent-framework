# Cross-Review: Implementation Plan Outline (Analyst Perspective)

**Reviewer**: rootcause-all (Analyst)
**Date**: 2026-05-12
**Document Reviewed**: `.designs/1/implementation-plan/implementation_plan_outline.md`

---

## CRITICAL

No critical issues found. The implementation plan is well-structured with clear phase dependencies, concrete acceptance criteria, and thorough codebase investigation in the "Current State" and "Gotchas" sections.

---

## HIGH

### H1: Round 1 Finding H3 (Rollback Strategy) Not Addressed in Plan

My round 1 review flagged that new Warning-level diagnostics (MAFGENWF008, MAFGENWF010, upgraded MAFGENWF006) will break consumer builds with `TreatWarningsAsErrors=true`. The plan acknowledges this risk in the Gotchas section (line 147: "TreatWarningsAsErrors=true in dotnet/Directory.Build.props") but proposes shipping as Warning anyway. The plan says "This is already the plan" but doesn't specify a rollback mechanism if consumer breakage is worse than expected.

- **Recommendation**: Add a rollback note: if MAFGENWF008/010 cause excessive consumer CI failures, they can be downgraded to Info in a patch release without behavioral change. This is a one-line severity change per diagnostic descriptor.

### H2: Incremental Caching Invalidation Risk for HandlerInfo Changes

The Gotchas section (line 148) correctly identifies that adding `DiagnosticLocationInfo` to `HandlerInfo` changes its value equality semantics, and recommends using `MethodAnalysisResult` location data instead. However, the Required Changes section for File 3 (HandlerInfo.cs, line 116-117) still lists adding a `MethodLocation` field as a possibility. This contradiction could lead an implementer to choose the wrong approach.

- **Recommendation**: Remove the "possibly" change to HandlerInfo.cs from Required Changes, or explicitly mark it as "DO NOT modify HandlerInfo — use MethodAnalysisResult locations instead" to match the Gotcha guidance.

### H3: Missing Validation Order Specification in Phase 1

The Gotchas section (line 151) specifies the correct validation order: (1) < 2 params, (2) > 3 params, (3) IWorkflowContext check, (4) CancellationToken/non-CT check. But the Required Changes section (lines 111-113) specifies insertions "After L480" and "After L493" without referencing this ordering constraint. An implementer reading Required Changes linearly might insert the 4+ param check after the existing < 2 check (correct), but could also misread the CancellationToken addition point.

- **Recommendation**: Add explicit ordering to Required Changes to match the Gotchas ordering, or reference the Gotcha by number.

---

## LOW

### L1: Phase 2 Multi-File Partial Class Test Already Exists — Plan Should Remove from Deliverables

The plan correctly identifies (line 180, line 225) that multi-file partial class tests already exist at lines 541-704. However, it's still listed as a Phase 2 deliverable in the design-doc Phase 2 section (referenced at line 170). The plan should explicitly state this deliverable is pre-satisfied and remove it from the implementation scope to avoid confusion about Phase 2 LOE.

### L2: No Cross-Reference Between Python Rootcause and .NET Generator Risks

This plan addresses a .NET source generator. My rootcause analysis covers a Python SDK event loop blocking bug. While these are different issues, both share a common pattern: **existing correct patterns in one part of the codebase not being applied to another** (Python: `FunctionExecutor` has `asyncio.to_thread()` but `FunctionTool` does not; .NET: source generator exists but no behavioral equivalence tests against the reflection path). The implementation plan could note this as a general codebase health observation, but this is informational, not actionable.

### L3: Acceptance Criteria Use `--no-build` Flag Inconsistently

Phase 1 acceptance criteria (lines 122-125) use `--no-build` for individual test filters but the full-suite test (line 138) does not. This means the individual tests assume a prior build step, but this isn't stated. Minor, but could cause confusion if someone runs the acceptance criteria standalone.

---

## Risk Coverage Assessment (vs. Rootcause Findings)

My rootcause analysis identified enforcement levels as a key quality measure. Mapping the plan's changes:

| Plan Change | Enforcement Level | Assessment |
|-------------|-------------------|------------|
| MAFGENWF008 (duplicate input types) | **Interlock** (compile-time) | Correct — catches runtime crash at build time |
| MAFGENWF009 (4+ params) | **Interlock** (compile-time Error) | Correct — prevents silent misconfiguration |
| MAFGENWF010 (non-CT third param) | **Runtime guard** (Warning, non-blocking) | Appropriate — handler still valid, user informed |
| MAFGENWF006 upgrade | **Runtime guard** (Warning) | Appropriate — progressive severity increase |
| Baseline comparison tests | **Runtime guard** | Good — catches regression in generated output |
| Migration guide | **Advisory** | Correct level for documentation |

The enforcement hierarchy is appropriate. No interlock-level changes are missing.

---

## Summary

The implementation plan is thorough and actionable. The main issue (H2) is a contradiction between Required Changes and Gotchas regarding HandlerInfo modification that could mislead implementers. The plan has excellent codebase investigation depth — exact file/line references, existing test discovery, and practical gotchas. All three phases have concrete acceptance criteria with verifiable commands.
