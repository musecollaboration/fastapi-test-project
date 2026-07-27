import logging
import sys

import structlog
from structlog.stdlib import add_logger_name
from structlog.types import Processor


def setup_logging():
    """Настройка структурированного логирования."""
    # Устанавливаем уровень логирования (можно читать из переменной окружения)
    log_level = logging.INFO

    # Процессоры определяют, как будет выглядеть конечный лог
    processors: list[Processor] = [
        structlog.stdlib.add_log_level,           # добавляет уровень (info, warning, error)
        add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),  # форматирует аргументы
        structlog.processors.TimeStamper(fmt="iso"),      # добавляет временную метку
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()               # преобразует в JSON
    ]

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Настройка стандартного logging для совместимости библиотек
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        stream=sys.stdout,
    )

    # Устанавливаем уровень для корневого логгера
    logging.getLogger().setLevel(logging.INFO)


def get_logger(name: str = __name__):
    """Получить логгер по имени"""
    return structlog.get_logger(name)
