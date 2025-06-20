# Changelog

## [0.2.0] - 2025-06-20

### Overview
- This release introduces a major refactor of the core proxy management logic, removing all static proxy lists and making LitProxy fully dynamic and remote-driven. The codebase is now simpler, more maintainable, and focused on fetching proxies from remote sources. The API is streamlined for modern usage, and documentation is updated for clarity and accuracy.

### Features

- **Remote-Only Proxy Management**
  - Removed all static proxy lists (Webshare, NordVPN, etc.) and related logic.
  - Now fetches proxies exclusively from a remote source (`PROXY_SOURCE_URL`).
  - Simplifies proxy rotation, testing, and cache management.
  - Files: `litproxy/core.py`, removed `litproxy/static_proxies.py`

- **Refactored Core Logic**
  - Rewrote proxy fetching, caching, and rotation to use only remote proxies.
  - Updated all helper functions and metaclass logic to reflect the new remote-only approach.
  - Improved error handling and cache refresh logic.
  - Files: `litproxy/core.py`

- **API Consistency & Modernization**
  - All public API functions (`proxy`, `get_proxy_dict`, `list_proxies`, etc.) now operate on the new remote-only backend.
  - Updated metaclass (`LitMeta`) and all session patching/auto-retry logic for consistency.
  - Files: `litproxy/core.py`, `litproxy/__init__.py`

### Improvements

- **Documentation Updates**
  - Updated `README.md` to reflect the new API and usage patterns.
  - Clarified that only remote proxies are now supported.
  - Improved code examples for context managers, decorators, and session patching.
  - Files: `README.md`

### Cleanup

- **Removed Legacy/Obsolete Files**
  - Deleted `litproxy/static_proxies.py` and all references to static proxy lists.
  - Files: `litproxy/static_proxies.py` (deleted), `litproxy/core.py`

### Refactoring

- **Wildcard Import in Package Init**
  - Changed `litproxy/__init__.py` to use `from .core import *` for full API exposure.
  - Files: `litproxy/__init__.py`

### Breaking Changes

- **No More Static Proxies**
  - All static proxy sources are removed. Users must ensure the remote proxy source is available.
  - Any code relying on static proxy lists will need to be updated.

### Other

- No changes to dependencies or project metadata.
- No changes to licensing.

---
## [0.1.3] - 2025-06-20

### Overview
- This release introduces package normalization, version bump, and documentation improvements to ensure consistency, clarity, and improved user experience. The changes align the project metadata, usage instructions, and licensing with best practices for Python packaging and open source distribution.

### Features & Improvements
- **Package Normalization & Version Update**
  - Updated `pyproject.toml`:
    - Changed project name from `Litproxy` to `litproxy` (PEP 8 compliance).
    - Bumped version from `0.1.0` to `0.1.3`.
    - Updated package discovery to use `litproxy*` and normalized the `where` field.
    - Ensured correct inclusion of package data and removed unnecessary fields.
  - Files: `pyproject.toml`

- **Documentation Fixes & Usage Consistency**
  - Fixed all import statements in `README.md` to use `from litproxy import ...` (lowercase, matching package name).
  - Added missing installation instructions for PyPI (`pip install litproxy`).
  - Improved code snippets and usage examples for clarity and accuracy.
  - Files: `README.md`

- **License Addition**
  - Added a standard MIT License file for open source compliance.
  - Files: `LICENSE`

### Other
- No changes to core logic or implementation in `litproxy/` modules.
- No changes to tests or dependencies beyond those listed above.

---
