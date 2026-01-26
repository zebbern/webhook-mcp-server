# Webhook MCP Server v2.0.5 - Improvement Plan

**Generated:** January 26, 2026  
**Based on:** 7-Parallel Subagent Analysis

---

## 📊 Current Scores

| Category      | Score  | Target |
| ------------- | ------ | ------ |
| Code Quality  | 78/100 | 90/100 |
| Security      | 73/100 | 85/100 |
| Performance   | 63/100 | 80/100 |
| API Design    | 79/100 | 85/100 |
| Documentation | 72/100 | 90/100 |
| Test Suite    | 62/100 | 80/100 |

---

## Phase 1: File Cleanup (Priority: HIGH) ✅ COMPLETED

### Files to DELETE

- [x] `scripts/check_webhook.py` - Personal debug script, not needed in package
- [x] `scripts/test_bugbounty_realworld.py` - Redundant with `tests/test_bugbounty.py`
- [x] `scripts/test_payload_functionality.py` - Redundant verification script
- [x] `tests/test_create.py` - Not a real test, just a debug script (18 lines)
- [x] `tests/test_real_world.py` - Duplicate of integration tests

**Estimated lines removed:** ~400+ lines ✅ DONE

---

## Phase 2: Dead Code Removal (Priority: HIGH) ✅ COMPLETED

### Unused Functions to DELETE

- [x] `utils/http_client.py`: Remove `get_http_client()` function (17 lines)
  - Never used anywhere in codebase
  - Redundant with `async with WebhookHttpClient()` pattern

- [x] `utils/validation.py`: Remove `sanitize_identifier()` function (~18 lines)
  - Defined but never called anywhere

### Unused Classes to DELETE

- [x] `models/schemas.py`: Remove `WebhookInfo` class (~36 lines)
  - Never instantiated anywhere
  - `create_webhook_with_config` returns dict directly

- [x] `models/schemas.py`: Remove `WebhookRequest` class (~35 lines)
  - Never instantiated
  - Has `from_api_response()` classmethod never called

### Unused Imports REMOVED

| File                 | Removed Import            |
| -------------------- | ------------------------- |
| `webhook_service.py` | `WebhookInfo` ✅           |
| `request_service.py` | `WebhookRequest` ✅        |
| `http_client.py`     | `asynccontextmanager`, `AsyncGenerator` ✅ |
| `models/__init__.py` | `WebhookInfo`, `WebhookRequest` ✅ |
| `utils/__init__.py`  | `sanitize_identifier` ✅   |

**Estimated lines removed:** ~120 lines ✅ DONE

---

## Phase 3: Documentation Fixes (Priority: HIGH)

### Missing Files to CREATE

- [ ] Create `LICENSE` file (MIT license)
- [ ] Create `CHANGELOG.md` (following Keep a Changelog format)
- [ ] Create `CONTRIBUTING.md` (extract from README)

### pyproject.toml Updates

- [ ] Add `readme = "README.md"`
- [ ] Add `license = {text = "MIT"}`
- [ ] Add `authors = [{name = "zebbern"}]`
- [ ] Add `keywords = ["mcp", "webhook", "testing", "model-context-protocol", "bugbounty"]`
- [ ] Add `classifiers` for Python versions and categories

### README.md Fixes

- [ ] Update tool count badge (16 → 21 or reduce tools)
- [ ] Add missing 5 bug bounty tools to documentation
- [ ] Fix version inconsistencies
- [ ] Add real code examples (not pseudo-code)
- [ ] Update dependency versions to match pyproject.toml

---

## Phase 4: Code Quality Improvements (Priority: MEDIUM)

### DRY Violations to Fix

- [ ] `webhook_service.py`: Extract URL building logic to private method
  - Duplicate code in `create_webhook` and `create_webhook_with_config`
  - ~20 lines duplicated

- [ ] `webhook_service.py`: Extract validation logic to helper method
  - Same validation in `get_url`, `get_email`, `get_dns`
  - ~60 lines duplicated (20 lines × 3)

### Import Organization

- [ ] Move inline imports to top of files in:
  - `tool_handlers.py` (lines 134, 148, 196)
  - `request_service.py` (lines 235-236, 342-343)
  - `bugbounty_service.py` (line 377)

### Missing Type Hints

- [ ] `tool_handlers.py` line 83: Add return type to `_get_handler()`
- [ ] Add return types to handler methods

### Magic Numbers to Constants

- [ ] `request_service.py`: `2.0` → `POLL_INTERVAL_SECONDS`
- [ ] `request_service.py`: `3` → `MAX_POLL_RETRIES`
- [ ] `request_service.py`: `10` → `DEFAULT_REQUESTS_LIMIT`
- [ ] `bugbounty_service.py`: `50` → `CALLBACK_FETCH_LIMIT`

---

## Phase 5: Performance Improvements (Priority: MEDIUM)

### Critical: HTTP Client Singleton

- [ ] Refactor `server.py` to use singleton HTTP client
  - Current: Creates new client per request (~100-300ms overhead)
  - Target: Reuse client with connection pooling

```python
# Proposed pattern
_client: WebhookHttpClient | None = None

async def get_shared_client() -> WebhookHttpClient:
    global _client
    if _client is None:
        _client = WebhookHttpClient()
        await _client.__aenter__()
    return _client
```

### HTTP Client Configuration

- [ ] Add httpx limits configuration:

  ```python
  limits=httpx.Limits(
      max_keepalive_connections=5,
      max_connections=10,
      keepalive_expiry=30.0
  )
  ```

- [ ] Add granular timeouts:
  ```python
  timeout=httpx.Timeout(
      connect=5.0,
      read=30.0,
      write=10.0,
      pool=5.0
  )
  ```

### Module-Level Optimizations

- [ ] Move handler mapping dict to class level (not recreated per call)
- [ ] Move logger setup to module level
- [ ] Precompile regex patterns in `bugbounty_service.py` and `request_service.py`

---

## Phase 6: API Design Improvements (Priority: LOW)

### Tools to MERGE

- [ ] Merge `create_webhook` into `create_webhook_with_config`
  - Make all config params optional
  - Rename to just `create_webhook`
  - Reduces tool count by 1

- [ ] Merge `get_webhook_requests` into `search_requests`
  - `get_webhook_requests` is subset of `search_requests`
  - Rename to `get_requests`
  - Reduces tool count by 1

### Tools to REMOVE (Optional)

- [ ] Consider removing `get_webhook_url`, `get_webhook_email`, `get_webhook_dns`
  - These are trivially constructed from token
  - Unless validation feature is valuable
  - Reduces tool count by 3

### Missing Tool Documentation

- [ ] Add these 5 tools to README:
  1. `search_requests`
  2. `send_to_webhook`
  3. `generate_xss_callback`
  4. `generate_canary_token`
  5. `quick_check`

---

## Phase 7: Test Improvements (Priority: LOW)

### Test Files to DELETE

- [ ] `tests/test_create.py` (covered in Phase 1)
- [ ] `tests/test_real_world.py` (covered in Phase 1)

### Test Files to MOVE

- [ ] `tests/manual_test.py` → `scripts/verify_tools.py`
- [ ] `tests/test_wait_tools.py` → `scripts/demo_wait.py`

### Missing Tests to ADD

- [ ] Create `tests/test_validation.py` for `utils/validation.py`
- [ ] Create `tests/test_schemas.py` for `models/schemas.py`
- [ ] Create `tests/conftest.py` with shared fixtures
- [ ] Add mock fixtures to decouple from live API

---

## Phase 8: Security Hardening (Priority: LOW)

### Improvements

- [ ] Add environment variable support for API key in `http_client.py`:

  ```python
  api_key = api_key or os.environ.get("WEBHOOK_SITE_API_KEY")
  ```

- [ ] Add timeout validation (max 300 seconds) in handlers
- [ ] Add missing token validation in `get_webhook_dns` handler
- [ ] Create `SECURITY.md` for vulnerability reporting

---

## Implementation Order

### Week 1: High Priority

1. Phase 1: File Cleanup
2. Phase 2: Dead Code Removal
3. Phase 3: Documentation Fixes

### Week 2: Medium Priority

4. Phase 4: Code Quality
5. Phase 5: Performance

### Week 3: Low Priority (Optional)

6. Phase 6: API Design
7. Phase 7: Tests
8. Phase 8: Security

---

## Version Plan

| Version | Changes                              | Type  |
| ------- | ------------------------------------ | ----- |
| v2.0.6  | File cleanup + dead code removal     | Patch |
| v2.1.0  | Documentation + pyproject.toml fixes | Minor |
| v2.2.0  | Performance improvements             | Minor |
| v3.0.0  | API changes (tool merging/removal)   | Major |

---

## Estimated Impact

After all improvements:

| Category      | Current | Target | Improvement |
| ------------- | ------- | ------ | ----------- |
| Code Quality  | 78      | 90     | +12         |
| Security      | 73      | 85     | +12         |
| Performance   | 63      | 80     | +17         |
| API Design    | 79      | 85     | +6          |
| Documentation | 72      | 90     | +18         |
| Test Suite    | 62      | 80     | +18         |
| **Average**   | **71**  | **85** | **+14**     |

**Lines of code removed:** ~610+ lines  
**Package size reduction:** ~15-20%
