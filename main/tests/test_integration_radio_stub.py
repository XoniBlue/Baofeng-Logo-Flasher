import pytest


@pytest.mark.skip(reason="Manual test: requires a connected radio")
def test_manual_radio_integration() -> None:
    assert True
