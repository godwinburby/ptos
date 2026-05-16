import pytest
import ptos


class TestValidateDateFormat:
    def test_indian_preset(self):
        assert ptos.validate_date_format("indian") is True

    def test_us_preset(self):
        assert ptos.validate_date_format("us") is True

    def test_eu_preset(self):
        assert ptos.validate_date_format("eu") is True

    def test_readable_preset(self):
        assert ptos.validate_date_format("readable") is True

    def test_iso_preset(self):
        assert ptos.validate_date_format("iso") is True

    def test_valid_strftime(self):
        assert ptos.validate_date_format("%Y-%m-%d") is True

    def test_complex_strftime(self):
        assert ptos.validate_date_format("%A, %d %B %Y") is True

    def test_invalid_no_percent(self):
        with pytest.raises(ValueError, match="not a preset"):
            ptos.validate_date_format("garbage")

    def test_invalid_ends_with_percent(self):
        with pytest.raises(ValueError, match="cannot end with %"):
            ptos.validate_date_format("%Y-%m-%")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            ptos.validate_date_format("")

    def test_just_percent_raises(self):
        with pytest.raises(ValueError, match="cannot end with %"):
            ptos.validate_date_format("%")
