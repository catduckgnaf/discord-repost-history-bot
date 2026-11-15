"""FeverDream - Discord bot for forwarding messages between servers.

Run: python bot.py  (see README.md for the full guide)
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from core.config import (
    DEV_GUILD_ID,
    DISCORD_TOKEN,
    HISTORY_REPOST_ENABLED,
    VERSION,
    extensions_for,
)
from core.forwarder import forward_message, is_forwardable, is_new_since_link
from core.jobs import JobManager
from core.storage import LinkStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("feverdream")

INTENTS = discord.Intents.default()
INTENTS.message_content = True  # required to read message content and attachments
INTENTS.guilds = True


class FeverDreamBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!feverdream ", intents=INTENTS, help_command=None)
        self.link_storage = LinkStorage()
        self.job_manager = JobManager()

    async def setup_hook(self) -> None:
        for extension in extensions_for(HISTORY_REPOST_ENABLED):
            await self.load_extension(extension)

        if DEV_GUILD_ID:
            guild = discord.Object(id=int(DEV_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Slash commands synced to development server %s", DEV_GUILD_ID)
        else:
            await self.tree.sync()
            log.info("Slash commands synced globally")

    async def on_ready(self) -> None:
        log.info("FeverDream %s logged in as %s (ID: %s)", VERSION, self.user, self.user.id)
        log.info(
            "History repost commands: %s",
            "enabled" if HISTORY_REPOST_ENABLED else "disabled (live forwarding only)",
        )
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching, name="/link-add | live forwarding"
        ))

    async def on_message(self, message: discord.Message) -> None:
        # Never handle our own messages or messages sent through a webhook
        # (otherwise linked channels could loop forever).
        if message.author == self.user or message.webhook_id is not None:
            return

        links = self.link_storage.get_targets_for_source(message.channel.id)
        for link in links:
            target = self.get_channel(link.target_channel_id)
            if target is None:
                log.warning("Target channel %s for link %s is not available", link.target_channel_id, link.id)
                continue
            if not is_forwardable(message):
                continue
            if not is_new_since_link(message, link.created_at):
                continue
            try:
                await forward_message(message, target)
            except discord.HTTPException as exc:
                log.error("Live forwarding of message %s failed: %s", message.id, exc)

        await self.process_commands(message)


def main() -> None:
    bot = FeverDreamBot()
    asyncio.run(bot.start(DISCORD_TOKEN))


if __name__ == "__main__":
    main()
