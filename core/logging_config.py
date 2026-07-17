"""Logging Config — structlog como backend real del logging estándar.

Antes: `structlog` estaba en requirements.txt (y mencionado en el README como
parte del stack) pero ningún módulo lo importaba; todo el sistema usaba
`logging.getLogger(__name__)` con el formatter por defecto de `logging.basicConfig`.

Ahora: configure_logging() envuelve el `logging` estándar con el
ProcessorFormatter de structlog. Esto NO requiere tocar los ~200 call sites de
`logger.info(...)` / `logger.warning(...)` ya existentes en agentes y core —
siguen siendo llamadas normales a `logging`, pero el output pasa por los
processors de structlog (timestamp ISO, nombre de agente, nivel, y JSON en
producción para que un log shipper pueda parsear campos estructurados).

Uso: llamar configure_logging(service_name) una vez, al inicio del proceso
(api/main.py y el bloque `if __name__ == "__main__":` de cada agente),
antes de crear cualquier logger.
"""
from __future__ import annotations

import logging
import os
import sys

import structlog


def configure_logging(service_name: str) -> None:
    is_production = os.environ.get("ENVIRONMENT", "development") == "production"

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = structlog.processors.JSONRenderer() if is_production else structlog.dev.ConsoleRenderer(colors=True)
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

    structlog.contextvars.bind_contextvars(service=service_name)
