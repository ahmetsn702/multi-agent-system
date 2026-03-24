# Preservation Property Test Observations

**Date**: Task 2 Execution
**Status**: ✅ All tests PASSED on unfixed code
**Purpose**: Document baseline behavior that must remain unchanged after implementing the fix

## Test Results Summary

All 9 preservation property tests passed on the unfixed code, confirming the baseline behavior to preserve.

## Observed Behaviors (UNFIXED Code)

### 1. High Score Approval (Score >= 7.0)
**Observation**: `critic.route_by_score(7.5, 0)` returns `"EXECUTOR"`

**Property-Based Test**: ANY score in range [7.0, 10.0] routes to `"EXECUTOR"`

**Test Coverage**: 20 generated examples, all passed

**Requirement**: 3.1 - This behavior MUST remain unchanged after the fix

---

### 2. Low Score Replan (Score < 4.0)
**Observation**: `critic.route_by_score(3.5, 0)` returns `"PLANNER_REPLAN"`

**Property-Based Test**: ANY score in range [0.0, 3.9] routes to `"PLANNER_REPLAN"`

**Test Coverage**: 20 generated examples, all passed

**Requirement**: 3.2 - This behavior MUST remain unchanged after the fix

---

### 3. Executor Context Enrichment
**Observation**: Executor tasks receive `all_previous_results` in their context

**Verified Behavior**:
- `orchestrator._enrich_task_context(executor_task, previous_results)` adds `all_previous_results` to `executor_task.context`
- The `all_previous_results` dict contains all completed task results indexed by task_id
- Executor needs this full context to know which files to run

**Requirement**: 3.3 - This behavior MUST remain unchanged after the fix (executor tasks need full context)

---

### 4. Normal Context Enrichment for Coder Tasks
**Observation**: Non-revision coder tasks receive research context

**Verified Behavior**:
- `orchestrator._enrich_task_context(coder_task, previous_results)` adds `research` field to `coder_task.context`
- Research context comes from completed researcher tasks
- This is normal context enrichment for initial (non-revision) coder tasks

**Requirement**: 3.4 - This behavior MUST remain unchanged after the fix (only revision tasks should have limited context)

---

### 5. Task Timeout Mechanism Exists
**Observation**: Orchestrator has `_execute_task` method that handles task execution

**Verified Behavior**:
- The timeout mechanism exists in the system
- The actual timeout value may change (180s -> 360s), but the mechanism should remain

**Requirement**: 3.5 - Tasks completing within timeout period should continue to process normally

---

### 6. Revision Count Tracking
**Observation**: `route_by_score` considers `revision_count` parameter

**Verified Behavior**:
- `route_by_score(5.0, 0)` returns `"CODER_REVISE"` (first revision)
- `route_by_score(5.0, 1)` returns `"CODER_REVISE"` (second revision)
- `route_by_score(5.0, 2)` returns `"EXECUTOR_ANYWAY"` (after 2 revisions, proceed anyway)

**Requirement**: 3.2 - Revision count logic must remain unchanged

---

### 7. Mid-Range Score Revision Logic (Score 4.0-6.9)
**Observation**: Scores in range [4.0, 6.9] with `revision_count < 2` route to `"CODER_REVISE"`

**Property-Based Test**: ANY score in [4.0, 6.9] with revision_count in [0, 1] routes to `"CODER_REVISE"`

**Test Coverage**: 20 generated examples, all passed

**Requirement**: 3.2 - This logic must remain unchanged (though the threshold may shift from 7.0 to 6.0)

---

## Key Insights for Fix Implementation

1. **Threshold Change Impact**: When lowering the approval threshold from 7.0 to 6.0, scores in [6.0, 6.9] will shift from `CODER_REVISE` to `EXECUTOR`. This is the intended fix, not a preservation violation.

2. **Context Enrichment Distinction**: The fix must distinguish between:
   - **Executor tasks**: Continue to receive `all_previous_results` (preserve)
   - **Revision coder tasks**: Should have limited context (fix)
   - **Initial coder tasks**: Continue to receive research context (preserve)

3. **Revision Count Logic**: The existing revision count logic (max 2 revisions, then `EXECUTOR_ANYWAY`) should remain unchanged.

4. **Timeout Mechanism**: The timeout mechanism exists and should be enhanced (180s -> 360s or reset on revision), but the basic mechanism should remain.

## Next Steps

These observations provide the baseline for implementing the fix in Task 3. The fix should:
- Lower the approval threshold from 7.0 to 6.0 (affects scores 6.0-6.9)
- Limit context for revision tasks only (preserve executor and initial coder context)
- Enhance timeout handling (preserve the mechanism, adjust the value or reset logic)
- Add file routing hints for conflicting tasks (preserve normal path resolution)

After implementing the fix, these preservation tests should still pass, confirming no regressions.
