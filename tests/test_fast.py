#!/usr/bin/env python
"""Fast test suite for pre-commit hooks (< 30s)."""
import pytest
import sys

if __name__ == "__main__":
    sys.exit(pytest.main([
        "tests/test_validate.py",
        "tests/test_parse.py",
        "tests/test_disp.py",
        "tests/test_value_normalisation.py",
        "tests/test_validate_format.py",
        "tests/test_parse_fast.py",
        "-m", "not slow",
        "-q",
        "--tb=line"
    ]))