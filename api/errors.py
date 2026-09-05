class AgentError(Exception):
    """Base class for all domain errors; maps to a specific HTTP response."""

    error: str = "agent_error"
    status_code: int = 500
    message: str = "Internal error"

class XuiError(AgentError):
    """3x-ui returned an error response or success=false."""

    error = "xui_error"
    status_code = 502
    message = "3x-ui API error"


class XuiUnavailableError(XuiError):
    """Cannot reach the 3x-ui panel at all (network/DNS/timeout)."""

    error = "xui_unavailable"
    status_code = 502
    message = "Cannot connect to 3x-ui"


class XuiClientNotFoundError(XuiError):
    """No VLESS client with the given external_id exists in 3x-ui."""

    error = "client_not_found"
    status_code = 404
    message = "VLESS client not found"


class XuiClientAlreadyExistsError(XuiError):
    """A VLESS client with this external_id already exists (idempotent create)."""

    error = "client_already_exists"
    status_code = 409
    message = "VLESS client already exists"

    def __init__(
        self,
        message: str | None = None,
        *,
        existing: dict | None = None,
    ) -> None:
        super().__init__(message or self.message)
        # Attach the full VlessUserResponse payload so the handler can
        # include it in the 409 response body without re-fetching.
        self.existing: dict | None = existing


class MtgConfigError(AgentError):
    """Cannot read or parse the mtg config.toml."""

    error = "mtg_config_error"
    status_code = 502
    message = "Cannot read MTProto config"
