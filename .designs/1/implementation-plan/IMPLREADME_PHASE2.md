# IMPLREADME Phase 2: Test Coverage Improvements

**Source**: `.designs/1/implementation-plan/implementation_plan_outline.md`
**Phase**: 2 of 3
**Recommended Skill**: `/ultra-implement`

## Objective

Add baseline comparison tests and diagnostic tests for Phase 1's new MAFGENWF008-010 diagnostics and the upgraded MAFGENWF006 severity.

## Changes Made

1. **3 baseline comparison tests** using `GetText()` for full generated output verification:
   - `Baseline_SingleVoidHandler_FullGeneratedOutput` — verifies complete ConfigureProtocol output structure
   - `Baseline_MultiHandlerMixedSignatures_FullGeneratedOutput` — verifies multi-handler with void + ValueTask<int>
   - `Baseline_FullProtocol_HandlersAndClassAttributes_FullGeneratedOutput` — verifies SendsMessage + YieldsOutput + handler

2. **4 new diagnostic tests**:
   - `DuplicateInputType_ProducesDiagnostic` — MAFGENWF008
   - `TooManyParameters_ProducesDiagnostic` — MAFGENWF009
   - `NonCancellationTokenThirdParam_ProducesDiagnostic` — MAFGENWF010
   - `ConfigureProtocolWarning_OnGenericExecutorBase_ProducesWarning` — MAFGENWF006 severity upgrade
   - `ConfigureProtocolInfo_OnPlainExecutorBase_ProducesInfo` — MAFGENWF006 Info severity preserved
