# Implementation Plan: Code Improvements

## Overview

Refactoring and hardening tasks across the Diagno-Pilot codebase covering security, architecture, code quality, performance, observability, and TypeScript improvements.

## Tasks

### Security

- [x] 1. Remove .env from git tracking and create .env.example
  - Run `git rm --cached .env` to untrack the file
  - Add `.env` to `.gitignore` if not already present
  - Create `.env.example` with all required keys and placeholder values (no real secrets)

- [x] 2. Add JWT_SECRET production validator in backend/core/config.py
  - Add a `@model_validator` (or `@validator`) that raises a `ValueError` when `JWT_SECRET` is set to a known-weak or default value in a non-development environment
  - Tie the check to an `ENV`/`ENVIRONMENT` setting so it only enforces in `production`

- [x] 3. Deduplicate get_current_user — remove local copy in backend/routers/auth.py
  - Delete the local `get_current_user` definition in `backend/routers/auth.py`
  - Add `from backend.core.auth import get_current_user` (or the equivalent relative import)
  - Verify all routes in `auth.py` that depend on the function still resolve correctly

### Architecture

- [x] 4. Extract compute_age_group into backend/utils/age.py
  - Create `backend/utils/__init__.py` if it does not exist
  - Create `backend/utils/age.py` and move `compute_age_group` there
  - Update both call sites (find with `grep -r compute_age_group backend/`) to import from `backend.utils.age`
  - Delete the original definition(s)

- [x] 5. Encapsulate memoryToken inside AuthProvider closure
  - In `apps/web/src/contexts/AuthContext.tsx` (and the mobile equivalent if applicable), move the `memoryToken` variable inside the `AuthProvider` component function body
  - Remove the module-level `let memoryToken` declaration
  - Verify the token is still correctly read and written within the closure

- [x] 6. Memoize createClient() in AuthContext.tsx
  - In `apps/web/src/contexts/AuthContext.tsx`, wrap the `createClient()` call with `useMemo` (or move it outside the render cycle) so a new client instance is not created on every render
  - Ensure the memoization dependencies are correct (typically an empty dependency array for a singleton client)

- [x] 7. Add seed dependency in docker-compose.yml
  - In `docker-compose.yml`, add a `depends_on` entry to the `backend` service that references the `seed` service with condition `service_completed_successfully`
  - Confirm the `seed` service is defined in the same compose file

### Code Quality

- [x] 8. Split backend/requirements.txt into prod and dev files
  - Create `backend/requirements-dev.txt` containing test/dev-only packages (pytest, hypothesis, httpx, etc.)
  - Remove those packages from `backend/requirements.txt`, leaving only production dependencies
  - Update `backend/Dockerfile` to install only `requirements.txt` (not the dev file)
  - Update any CI scripts or README references that install requirements

- [x] 9. Fix RAGService context serialization
  - In `backend/services/rag_service.py`, find the `str(model_dump())` call used to serialize context objects
  - Replace it with `.model_dump_json()` to produce valid JSON instead of a Python `repr` string

- [x] 10. Replace emoji hamburger icons in NavBar.tsx with SVG icons
  - In `apps/web/src/components/NavBar.tsx`, locate the emoji character(s) used as the hamburger menu icon
  - Replace with an inline SVG (three horizontal lines) or import an icon from the existing UI package
  - Ensure the replacement is accessible (add `aria-label` or `aria-hidden` as appropriate)

- [x] 11. Fix datetime.min.time() usage in patient_service.py
  - In `backend/services/patient_service.py`, find usages of `datetime.min.time()` or `datetime.combine(date, datetime.min.time())`
  - Replace with `datetime.combine(date, time.min)` (importing `time` from `datetime`) or `datetime(year, month, day, 0, 0, 0)` as appropriate
  - Confirm the fix does not change the intended midnight-boundary semantics

### Performance

- [x] 12. Add MongoDB indexes for patients.created_by in lifespan
  - In `backend/main.py`, inside the `lifespan` async context manager (or startup handler), add an `ensure_index` / `create_index` call on the `patients` collection for the `created_by` field
  - Use `background=True` to avoid blocking startup

- [x] 13. Make LLM timeout configurable via Settings
  - In `backend/core/config.py`, add an `LLM_TIMEOUT` field (e.g., `int`, default `30`) to the `Settings` model
  - In `backend/services/llm_router.py` (or wherever the LLM client is instantiated), replace the hard-coded timeout value with `settings.LLM_TIMEOUT`
  - Add `LLM_TIMEOUT` to `.env.example`

### Observability

- [x] 14. Fix start.sh .env loading
  - In `start.sh`, replace the current `.env` sourcing approach with:
    ```sh
    set -a
    source .env
    set +a
    ```
  - This ensures all variables are exported to child processes automatically

- [x] 15. Move circuit_breaker metrics import to module level
  - In `backend/core/circuit_breaker.py`, find any `import` statement for metrics that lives inside a function body
  - Move it to the top of the file with the other module-level imports
  - Verify no circular import is introduced (run the test suite)

### TypeScript / Types

- [x] 16. Centralize AuthUser in @diagno-pilot/types and remove duplicates
  - In `packages/types/index.ts`, define (or confirm) the canonical `AuthUser` type
  - Remove duplicate `AuthUser` definitions from `apps/web/src/contexts/AuthContext.tsx`, `apps/mobile/src/contexts/AuthContext.tsx`, and any other locations found via `grep -r "AuthUser" apps/`
  - Update all import sites to pull from `@diagno-pilot/types`

- [x] 17. Add AbortSignal support to api-client methods
  - In `packages/api-client/index.ts`, add an optional `signal?: AbortSignal` parameter to each public request method (GET, POST, PUT, DELETE or equivalent)
  - Pass the signal through to the underlying `fetch` call
  - Update `packages/api-client/index.test.ts` with a test that verifies a request is aborted when the signal fires
