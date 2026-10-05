"""A licence that is accidentally truncated is a legal problem, not a build
failure, so pin that it is present and intact."""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LICENSE = os.path.join(REPO, "LICENSE")


def _text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestLicense:
    def test_file_exists(self):
        assert os.path.exists(LICENSE)

    def test_is_mit_and_notices_the_holder(self):
        text = _text(LICENSE)
        assert text.startswith("MIT License")
        assert "Copyright (c) 2026 godwinburby" in text

    def test_keeps_the_four_mit_clauses(self):
        # Removing any one of these changes what the licence grants.
        text = _text(LICENSE)
        for clause in (
            "Permission is hereby granted, free of charge",       # grant
            "shall be included in all",                            # attribution
            "WITHOUT WARRANTY OF ANY KIND",                        # no warranty
            "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM",  # no liability
        ):
            assert clause in text, clause

    def test_grant_is_not_a_closed_licence(self):
        # "without restriction" and the sell sub-clause are what make this
        # permissive; a copy-paste slip that dropped them would silently
        # forbid redistribution.
        text = _text(LICENSE)
        assert "without restriction" in text
        assert "distribute, sublicense, and/or sell" in text

    def test_readme_links_it(self):
        assert "LICENSE" in _text(os.path.join(REPO, "README.md"))