"""Phone-region detection uses real libphonenumber metadata in CI/Docker."""
import pytest

pytest.importorskip("phonenumbers")

from backend.utils.phone_country import country_code_from_phone  # noqa: E402


@pytest.mark.parametrize(
    ("phone", "country"),
    [
        ("+86 138 0013 8000", "CN"),
        ("12025550123", "US"),
        ("+44 20 7946 0958", "GB"),
        (None, None),
        ("123", None),
    ],
)
def test_country_code_from_phone(phone, country):
    assert country_code_from_phone(phone) == country
