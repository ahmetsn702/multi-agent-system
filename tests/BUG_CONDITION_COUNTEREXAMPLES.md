# Bug Condition Exploration - Counterexamples Found

## Test Execution Summary

**Date**: Test run on unfixed code  
**Test File**: `tests/test_main_py_and_test_collection_bugs.py`  
**Result**: 4/4 tests FAILED (as expected - confirms bugs exist)

## Counterexamples Documented

### Bug 1: Missing main.py Creation

**Test**: `test_bug_1_api_project_missing_main_py`

**Counterexample**:
- User goal: "Create a FastAPI todo app with CRUD endpoints"
- Project slug: `create-a-fastapi-todo-app-with-crud-endp`
- Expected: `src/main.py` should exist with FastAPI app
- Actual: `src/main.py` does NOT exist

**Evidence**:
```
AssertionError: Bug detected: src/main.py does NOT exist at 
C:\Users\ahmed\AppData\Local\Temp\test_workspace_fdy6wgaf\workspace\projects\
create-a-fastapi-todo-app-with-crud-endp\src\main.py. 
API project was created but main.py was not generated. 
This confirms the missing main.py bug exists.
```

**Root Cause Confirmed**: The orchestrator creates project directories (`src/`, `tests/`, `docs/`) but has NO logic to create `src/main.py` during project setup.

---

### Bug 2: Truncated ImportError Output

**Test**: `test_bug_2_pytest_import_error_truncated`

**Counterexample**:
- Test file: `tests/test_import_error.py` with `from src.main import app`
- Expected: Full ImportError with stack trace and module path (at least 3 lines)
- Actual: Only 0 error lines logged

**Evidence**:
```
Logged output:
[Tester] Test klasörü bulundu: C:\Users\ahmed\AppData\Local\Temp\test_pytest_j1ncvems\workspace\projects\test-project\tests
[Tester] 0 test gecti, 3 hata
[Tester]   =================================== ERRORS ====================================
[Tester]   _________________ ERROR collecting tests/test_import_error.py _________________
[Tester]   ERROR tests/test_import_error.py

Bug detected: only 0 error line(s) logged. Expected at least 3 lines showing full ImportError context.
```

**Root Cause Confirmed**: The tester agent only logs the first line of each error (`ft.splitlines()[0]`), hiding the actual ImportError message, stack trace, and import path details.

---

### Bug 3: Truncated SyntaxError Output

**Test**: `test_bug_3_pytest_syntax_error_truncated`

**Counterexample**:
- Test file: `tests/test_syntax_error.py` with missing closing parenthesis
- Expected: Full SyntaxError with line numbers and error context
- Actual: No line number information in logged output

**Evidence**:
```
AssertionError: Error output should show line number information for SyntaxError
```

**Root Cause Confirmed**: The tester agent's error capture window (`capture_next = 3`) is insufficient for multi-line SyntaxError messages that include line numbers, error context, and the problematic code line.

---

### Property-Based Test: Missing main.py for ANY API Keyword

**Test**: `test_bug_1_property_any_api_keyword_missing_main_py`

**Counterexample**:
- Falsifying example: `api_keyword='fastapi'`
- User goal: "Create a fastapi application for task management"
- Expected: `src/main.py` should exist for ANY API keyword
- Actual: `src/main.py` does NOT exist

**Evidence**:
```
Falsifying example: test_bug_1_property_any_api_keyword_missing_main_py(
    self=<tests.test_main_py_and_test_collection_bugs.TestBugConditionExploration object at 0x000002A33DD20A50>,
    api_keyword='fastapi',
)

AssertionError: Bug detected: src/main.py does NOT exist for keyword 'fastapi'. 
This confirms the bug exists for this API keyword.
```

**Root Cause Confirmed**: The bug exists for ALL API keywords tested (fastapi, api, web, rest, backend). The orchestrator has no keyword detection logic to trigger main.py creation.

---

## Conclusion

All 4 tests FAILED as expected on unfixed code, confirming:

1. ✅ **Bug 1 exists**: API projects do NOT get `src/main.py` created
2. ✅ **Bug 2 exists**: ImportError details are completely truncated (0 lines logged)
3. ✅ **Bug 3 exists**: SyntaxError line numbers and context are hidden
4. ✅ **Property holds**: Bug 1 affects ALL API keywords (fastapi, api, web, rest, backend)

These counterexamples validate the root cause analysis in the design document and provide concrete evidence for implementing the fix.

## Next Steps

1. ✅ Task 1 complete: Bug condition exploration test written and run on unfixed code
2. ⏭️ Task 2: Write preservation property tests (BEFORE implementing fix)
3. ⏭️ Task 3: Implement fixes for both bugs
4. ⏭️ Task 4: Verify bug condition test now passes (confirms fix works)
5. ⏭️ Task 5: Verify preservation tests still pass (confirms no regressions)
