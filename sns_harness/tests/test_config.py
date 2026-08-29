from sns_harness.config import Settings


def test_comma_separated_default_slots_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DEFAULT_SLOTS", "08:30,18:30")
    monkeypatch.setenv("TZ", "Asia/Seoul")

    settings = Settings(_env_file=None)

    assert settings.default_slots == ("08:30", "18:30")
    assert settings.tz.key == "Asia/Seoul"
