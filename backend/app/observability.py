import sentry_sdk

from app.config import Settings


def init_sentry(settings: Settings) -> bool:
    """Error monitoring and tracing, only when a DSN is configured.

    send_default_pii stays off: in local mode customer names and messages must not leave the
    machine, so request bodies, headers and IPs are not attached to events.
    """
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    return True
