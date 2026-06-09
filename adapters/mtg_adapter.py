"""Adapter for mtg (MTProto proxy).

mtg v2 has no management API — it runs with a single static secret stored in
config.toml.  This adapter only reads that file and builds the tg:// link.
All operations are synchronous and cheap (single file read per call).
"""

import tomllib

from core.config import settings


class MtgConfigError(Exception):
    """Raised when the mtg config cannot be read or is missing required fields."""


class MtgAdapter:
    def __init__(self, config_path: str, server_ip: str, port: int) -> None:
        self.config_path = config_path
        self.server_ip = server_ip
        self.port = port

    def get_proxy_info(self) -> dict:
        """Read config.toml and return proxy connection details.

        Returns:
            {
                "server":  str   — public IP of this VPN server,
                "port":    int   — MTProto port (usually 2443),
                "secret":  str   — hex secret from config.toml,
                "tg_link": str   — ready-to-use tg://proxy?... URI,
            }

        Raises:
            MtgConfigError: if the file is absent, malformed, or has no `secret`.
        """
        try:
            with open(self.config_path, "rb") as fh:
                config = tomllib.load(fh)
        except FileNotFoundError:
            raise MtgConfigError(
                f"MTProto config not found: {self.config_path}"
            )
        except tomllib.TOMLDecodeError as exc:
            raise MtgConfigError(
                f"MTProto config is not valid TOML ({self.config_path}): {exc}"
            )

        secret: str | None = config.get("secret")
        if not secret:
            raise MtgConfigError(
                f"MTProto config has no 'secret' field: {self.config_path}"
            )

        tg_link = (
            f"tg://proxy?server={self.server_ip}&port={self.port}&secret={secret}"
        )
        return {
            "server": self.server_ip,
            "port": self.port,
            "secret": secret,
            "tg_link": tg_link,
        }

    def check_health(self) -> str:
        """Return 'ok' if the config is readable and valid, 'offline' otherwise."""
        try:
            self.get_proxy_info()
            return "ok"
        except MtgConfigError:
            return "offline"


# Module-level singleton — stateless and cheap, no lifespan needed.
mtg_adapter = MtgAdapter(
    config_path=settings.MTG_CONFIG_PATH,
    server_ip=settings.MTG_SERVER_IP,
    port=settings.MTG_PORT,
)
