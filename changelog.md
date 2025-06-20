# Changelog

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
