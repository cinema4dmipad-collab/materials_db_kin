"""Реестр динамически зарегистрированных моделей (managed=False)."""

REGISTERED_MODELS: dict[str, type] = {}
