from dataclasses import replace

import sentry_sdk

from app.observability import init_sentry


def test_sentry_stays_off_without_a_dsn(settings):
    assert init_sentry(replace(settings, sentry_dsn=None)) is False


def test_sentry_never_sends_default_pii(settings, monkeypatch):
    captured = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: captured.update(kw))
    dsn = "https://public@o0.ingest.sentry.io/0"
    assert init_sentry(replace(settings, sentry_dsn=dsn)) is True
    assert captured["send_default_pii"] is False
    assert captured["dsn"] == dsn
