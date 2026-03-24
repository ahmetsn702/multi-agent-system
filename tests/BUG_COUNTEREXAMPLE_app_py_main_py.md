# Bug Condition Counterexamples - app.py vs main.py Import Fix

## Test Execution Date
2024 (Unfixed Code)

## Bug Confirmed: YES ✓

The bug condition exploration test **FAILED as expected**, confirming the bug exists in the unfixed code.

## Counterexample Found

### Test Case: `test_bug_app_py_without_main_py_causes_import_error`

**Setup:**
- Project has `src/app.py` with FastAPI app
- Project does NOT have `src/main.py`
- Test file contains `from main import app`

**Expected Behavior (after fix):**
- Test should pass (either main.py exists as shim, or imports are correct)

**Actual Behavior (unfixed code):**
- Test fails with `ModuleNotFoundError: No module named 'main'`
- Exit code: 2
- Error occurs during test collection phase

**Error Output:**
```
ImportError while importing test module
Traceback:
workspace\projects\test-app-py-only\tests\test_api.py:6: in <module>
    from main import app
E   ModuleNotFoundError: No module named 'main'
```

## Root Cause Analysis

The counterexample confirms the hypothesized root causes:

1. **Hardcoded Import Assumption**: Test files are generated with `from main import app` regardless of which file actually exists in the project

2. **Missing Post-Execution Hook**: The orchestrator does not verify that `main.py` exists after all phases complete, even when only `app.py` was created

3. **No Filename Detection**: There is no logic to check whether `main.py` or `app.py` exists before generating import statements

## Impact

This bug causes:
- ImportError when running tests for projects that use `app.py` instead of `main.py`
- Test collection failures that prevent any tests from running
- Confusion for users who follow common FastAPI patterns (using `app.py`)

## Next Steps

1. ✓ Bug condition confirmed through failing test
2. Implement fix as specified in design.md:
   - Add `_ensure_main_py()` method to orchestrator
   - Call it after phases complete
   - Update coder agent system prompt for filename detection
3. Re-run this test to verify fix (test should pass after fix)
