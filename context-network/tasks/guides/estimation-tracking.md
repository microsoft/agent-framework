# Estimation Tracking

How to track estimated vs actual time, calculate variance, and improve future estimates.

## Why Track Estimates

1. **Improve Accuracy**: Learn from past estimates to make better future ones
2. **Identify Patterns**: Discover which types of tasks are consistently under/over-estimated
3. **Resource Planning**: Better predict project timelines
4. **Agent Performance**: Understand agent execution efficiency

## Estimation Format

### Initial Estimate
```markdown
**Estimated Effort**: 4 hours
**Estimated By**: [Name/Agent ID]
**Estimation Date**: 2025-10-11
**Confidence**: Medium (Low/Medium/High)
```

### Actual Tracking
```markdown
**Actual Effort**: 5.5 hours
**Completed By**: [Name/Agent ID]
**Completion Date**: 2025-10-12
**Variance**: +1.5 hours (+37%)
```

## Variance Calculation

```
Variance (hours) = Actual - Estimated
Variance (%) = (Actual - Estimated) / Estimated × 100
```

### Examples
- Estimated: 4h, Actual: 5.5h → **+1.5h (+37%)**
- Estimated: 6h, Actual: 4h → **-2h (-33%)**
- Estimated: 3h, Actual: 3.2h → **+0.2h (+7%)**

## Variance Classification

### Green: Within Tolerance (±20%)
- **±0-20%**: Estimate was accurate
- **Action**: No adjustment needed

### Yellow: Moderate Variance (20-50%)
- **+20-50%**: Task took longer than expected
- **-20-50%**: Task was faster than expected
- **Action**: Review to understand why

### Red: High Variance (>50%)
- **>+50%**: Significant underestimate
- **>-50%**: Significant overestimate
- **Action**: Analyze root cause and adjust methodology

## Tracking Template

Add to the bottom of each completed task:

```markdown
---

## Execution Tracking

### Estimation
**Estimated Effort**: 4 hours
**Estimated By**: Claude Code
**Estimation Date**: 2025-10-11
**Confidence**: Medium
**Estimation Basis**: Similar to TASK-002, with added complexity for validation

### Actual
**Actual Effort**: 5.5 hours
**Completed By**: Developer X / Agent Y
**Start Time**: 2025-10-12 09:00
**End Time**: 2025-10-12 14:30
**Completion Date**: 2025-10-12

### Variance Analysis
**Time Variance**: +1.5 hours (+37%)
**Classification**: 🟨 Yellow (Moderate)

**Breakdown**:
- Implementation: 3h (estimated 2.5h)
- Testing: 1.5h (estimated 1h)
- Debugging: 0.5h (estimated 0.25h)
- Documentation: 0.5h (estimated 0.25h)

**Variance Reasons**:
1. Additional edge cases discovered during testing (not in spec)
2. Type inference issues required more complex type guards
3. Integration with existing types had unexpected complexity

**Lessons Learned**:
- Add 30% buffer for tasks involving complex type inference
- Edge cases should be explicitly listed in task requirements
- Consider integration complexity in initial estimate

**Estimation Accuracy for Future**:
- Similar tasks: Add +30% for type-heavy work
- Similar tasks: Explicitly enumerate edge cases first
```

## Aggregate Metrics

Track metrics across all tasks:

### Phase Summary
```markdown
## Phase 1 Estimation Summary

| Task | Est | Act | Var | Var % | Status |
|------|-----|-----|-----|-------|--------|
| 001  | 3h  | 3h  | 0h  | 0%    | 🟢     |
| 002  | 4h  | 5.5h| +1.5h| +37% | 🟨     |
| 003  | 3h  | 2.5h| -0.5h| -17% | 🟢     |
| 004  | 3h  | 4.5h| +1.5h| +50% | 🟨     |
| ... | ... | ... | ... | ...   | ...    |

**Phase Totals**:
- Estimated: 55h
- Actual: 63h
- Variance: +8h (+15%)

**Average Variance**: +15%
**Median Variance**: +12%
**Tasks in Tolerance**: 8/13 (62%)
```

## Root Cause Categories

Track variance reasons in categories:

### Common Underestimation Causes
1. **Scope Creep**: Requirements expanded during implementation
2. **Technical Complexity**: Unexpected technical challenges
3. **Integration Issues**: Integration harder than expected
4. **Edge Cases**: More edge cases than anticipated
5. **Tooling Problems**: Build/test/type issues
6. **Learning Curve**: Unfamiliarity with tools/patterns

### Common Overestimation Causes
1. **Experience**: More familiarity than expected
2. **Reuse**: Found reusable code/patterns
3. **Simpler Than Expected**: Problem was simpler
4. **Good Tooling**: Tools worked better than expected

## Variance Tracking Dashboard

```markdown
## Project Estimation Dashboard

### Overall Stats
- **Total Tasks**: 50
- **Completed**: 23
- **Average Variance**: +12%
- **Median Variance**: +8%
- **Within Tolerance**: 65%

### By Phase
| Phase | Est | Act | Var | Accuracy |
|-------|-----|-----|-----|----------|
| 1     | 55h | 63h | +8h | 85%      |
| 2     | 38h | 42h | +4h | 89%      |
| 3     | 50h | -   | -   | -        |
| 4     | 60h | -   | -   | -        |
| 5     | 55h | -   | -   | -        |

### By Task Type
| Type | Avg Est | Avg Act | Avg Var |
|------|---------|---------|---------|
| Types/Interfaces | 3.5h | 3.2h | -9% |
| Core Classes | 5.5h | 6.8h | +24% |
| Integration | 4.0h | 5.5h | +37% |
| Tests Only | 2.5h | 2.2h | -12% |

### By Executor
| Executor | Tasks | Avg Var | Best | Worst |
|----------|-------|---------|------|-------|
| Agent A | 10 | +15% | +2% | +45% |
| Dev X | 8 | +5% | -10% | +20% |
| Dev Y | 5 | +25% | +10% | +50% |
```

## Calibration Process

### Initial Estimates (Tasks 1-5)
- Use spec-based estimation
- Apply standard rates (see below)
- Document assumptions

### Mid-Project Calibration (After 5-10 tasks)
- Calculate average variance
- Adjust future estimates by variance percentage
- Update standard rates

### Ongoing Refinement (Every 5 tasks)
- Review variance trends
- Identify systematic errors
- Update estimation methodology

## Standard Estimation Rates

Use these as starting points (adjust based on variance tracking):

### By Task Complexity

**Simple (2-3h)**:
- Single interface definition
- Basic type definitions
- Simple utility functions
- Straightforward tests

**Moderate (4-6h)**:
- Class implementation
- Multiple related types
- Integration work
- Comprehensive test suite

**Complex (6-8h)**:
- Multi-class system
- Complex state management
- Advanced TypeScript features
- Full integration tests

### By Component Type

**Types/Interfaces**: 0.5-1h per interface + 1h tests
**Classes**: 2-4h per class + 1-2h tests
**Integration**: 3-5h per integration point
**Documentation**: 0.5-1h per major component

### Adjustment Factors

**Multiply estimate by:**
- **1.3x** if involving complex type inference
- **1.2x** if first implementation of pattern
- **1.5x** if integration with external systems
- **1.2x** if agent executor (vs human developer)
- **0.8x** if following established pattern
- **0.9x** if experienced with similar work

### Example Calculation
```
Base: Implement ChatMessage types (4h)
× 1.3 (complex type inference)
× 0.9 (following Python reference)
= 4.68h → Round to 5h

Confidence: Medium (applying adjustment factors)
```

## Confidence Levels

### High Confidence (±10%)
- Very similar to completed work
- Well-understood requirements
- Established patterns
- No unknowns

### Medium Confidence (±20%)
- Somewhat similar to past work
- Clear requirements
- Some new patterns
- Few unknowns

### Low Confidence (±50%)
- New territory
- Unclear requirements
- Novel patterns
- Many unknowns

**Include confidence in estimate**:
```markdown
**Estimated Effort**: 5 hours (Medium confidence)
```

## Time Tracking Best Practices

### Start/Stop Tracking
```markdown
**Start**: 2025-10-12 09:00
**End**: 2025-10-12 14:30
**Breaks**: 30 min
**Net Time**: 5h
```

### Activity Breakdown
Track time by activity:
```markdown
- Requirements analysis: 0.5h
- Implementation: 3.0h
- Testing: 1.0h
- Documentation: 0.5h
- **Total**: 5.0h
```

### Interruption Tracking
Note significant interruptions:
```markdown
**Interruptions**:
- Code review request: 15 min
- Build system issue: 20 min
- **Net interruptions**: 35 min (not counted in task time)
```

## Retrospective Template

After completing 5-10 tasks, conduct a retrospective:

```markdown
## Estimation Retrospective - Tasks 001-010

**Date**: 2025-10-15
**Participants**: Team / Agent

### Metrics
- Completed: 10 tasks
- Total Estimated: 45h
- Total Actual: 52h
- Overall Variance: +7h (+15%)

### What Went Well
- Type-only tasks were accurately estimated (±5%)
- Following Python reference reduced variance
- Clear requirements led to better estimates

### What Went Wrong
- Underestimated integration complexity by 30-40%
- Type inference issues added unexpected time
- Edge cases not fully considered in estimates

### Adjustments for Next 10 Tasks
1. Add 30% to any task involving external integration
2. Add 20% to tasks with complex type inference
3. Require explicit edge case enumeration before estimation
4. Use reference implementation complexity as calibration

### Updated Estimation Rules
- Integration tasks: Base × 1.3
- Type-heavy tasks: Base × 1.2
- Following established pattern: Base × 0.9
```

## Tools and Automation

### Suggested Tools
- **Time Tracking**: Toggl, Clockify, or simple markdown log
- **Spreadsheet**: Google Sheets for aggregate metrics
- **Scripts**: Automate variance calculation from markdown

### Example Script (Pseudo)
```bash
# Parse completed tasks and calculate metrics
grep -A 20 "## Execution Tracking" tasks/**/*.md | \
  extract_estimates | \
  calculate_variance | \
  generate_dashboard
```

## Learning Loop

```
Estimate → Execute → Track → Analyze → Adjust → Estimate (better)
```

**Key**: The loop only works if you consistently track and analyze. Don't skip the tracking step even when tasks go smoothly.
