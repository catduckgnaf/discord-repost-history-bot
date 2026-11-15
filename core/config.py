"""Bot configuration loaded from the environment (.env)."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

VERSION = "0.0.1"


def env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable (1/true/yes/on, case-insensitive)."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().strip("\"'").lower() in {"1", "true", "yes", "on"}


DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
DEV_GUILD_ID: str | None = os.getenv("DEV_GUILD_ID") or None

# Bulk history reposting (/repost-history, /repost-status, /repost-stop) is
# OFF by default so the bot only forwards messages posted going forward.
# Set ENABLE_HISTORY_REPOST=true to register those commands again.
HISTORY_REPOST_ENABLED: bool = env_flag("ENABLE_HISTORY_REPOST", False)

# How many messages to process between progress-update edits.
PROGRESS_UPDATE_EVERY = 25

# Pause between individual sends during bulk repost/broadcast so the bot
# does not hit Discord rate limits.
SEND_DELAY_SECONDS = 0.8

# Name of the webhook the bot uses to repost messages under the original
# author's name and avatar.
WEBHOOK_NAME = "FeverDream Relay"


def extensions_for(history_enabled: bool) -> tuple[str, ...]:
    """Cogs to load. The history repost cog is only loaded when enabled."""
    extensions = ["cogs.linking", "cogs.broadcast"]
    if history_enabled:
        extensions.insert(1, "cogs.repost")
    return tuple(extensions)


if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is not set. Copy .env.example to .env and paste your bot token."
    )
