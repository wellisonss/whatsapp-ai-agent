"""Exceções de domínio."""


class ChatbotError(Exception):
    """Base."""


class ConfigError(ChatbotError):
    pass


class IntegrationError(ChatbotError):
    pass


class WahaError(IntegrationError):
    pass


class ErpError(IntegrationError):
    pass


class ToolError(ChatbotError):
    pass
