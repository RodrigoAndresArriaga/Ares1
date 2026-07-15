# structured application logging (stdlib only)
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings

_CONFIGURED = False
_HANDLER_MARKER = "ares_structured_handler"


# UTC ISO timestamp for structured records
class UtcFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras: list[str] = []
        event = getattr(record, "event", None)
        if event is not None:
            extras.append(f"event={event}")
        for key in (
            "run_id",
            "scenario_id",
            "plan_id",
            "mode",
            "duration_ms",
            "process_exit_code",
            "outcome",
            "error_code",
        ):
            value = getattr(record, key, None)
            if value is not None:
                extras.append(f"{key}={value}")
        if extras:
            return f"{base} {' '.join(extras)}"
        return base


# configure root ares loggers once from settings
def configure_logging(settings: Settings) -> None:
    global _CONFIGURED
    root = logging.getLogger("ares")
    level = getattr(logging, settings.log_level, logging.INFO)
    root.setLevel(level)

    existing = [
        h
        for h in root.handlers
        if getattr(h, _HANDLER_MARKER, False)
    ]
    if existing:
        for handler in existing:
            handler.setLevel(level)
        _CONFIGURED = True
        return

    handler = logging.StreamHandler()
    setattr(handler, _HANDLER_MARKER, True)
    handler.setLevel(level)
    handler.setFormatter(
        UtcFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        ),
    )
    root.addHandler(handler)
    # keep propagate True so pytest caplog and host loggers receive records
    _CONFIGURED = True


# emit a structured run event on the given logger
def log_run_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    event: str,
    **context: Any,
) -> None:
    extras = {"event": event}
    for key, value in context.items():
        if value is not None:
            extras[key] = value
    logger.log(level, message, extra=extras)
