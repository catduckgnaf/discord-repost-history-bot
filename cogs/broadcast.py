"""Command for sending one message (optionally with an attachment) to many channels at once."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from core.config import SEND_DELAY_SECONDS

if TYPE_CHECKING:
    from bot import FeverDreamBot


class BroadcastCog(commands.Cog):
    def __init__(self, bot: "FeverDreamBot") -> None:
        self.bot = bot

    def _parse_channel_ids(self, raw: str) -> list[int]:
        ids: list[int] = []
        for token in raw.replace("<#", "").replace(">", "").split(","):
            token = token.strip()
            if not token:
                continue
            try:
                ids.append(int(token))
            except ValueError:
                continue
        return ids

    @app_commands.command(
        name="broadcast",
        description="Send the same message (optionally with an attachment) to several channels at once.",
    )
    @app_commands.describe(
        message="Message text to send to every selected channel.",
        channel_ids="Comma-separated channel IDs (e.g. 123,456,789) or #channel mentions.",
        attachment="Optional attachment (photo/video/file) added to every message.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def broadcast(
        self,
        interaction: discord.Interaction,
        message: str,
        channel_ids: str,
        attachment: discord.Attachment | None = None,
    ) -> None:
        ids = self._parse_channel_ids(channel_ids)
        if not ids:
            await interaction.response.send_message("Could not recognize any channel IDs.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        sent, failed = 0, []
        for channel_id in ids:
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.abc.Messageable):
                failed.append(channel_id)
                continue
            try:
                file = await attachment.to_file() if attachment else None
                await channel.send(content=message, file=file)
                sent += 1
            except discord.HTTPException:
                failed.append(channel_id)
            await asyncio.sleep(SEND_DELAY_SECONDS)

        embed = discord.Embed(
            title="✅ Broadcast sent - the job is done!",
            color=discord.Color.green() if not failed else discord.Color.orange(),
        )
        embed.add_field(name="Sent successfully", value=str(sent), inline=True)
        embed.add_field(name="Failed", value=str(len(failed)), inline=True)
        if failed:
            embed.add_field(name="Unavailable channels", value=", ".join(f"`{c}`" for c in failed), inline=False)

        await interaction.followup.send(embed=embed)

    @broadcast.error
    async def on_permission_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You need the **Manage Guild** permission to use this command.", ephemeral=True
            )
        else:
            raise error


async def setup(bot: "FeverDreamBot") -> None:
    await bot.add_cog(BroadcastCog(bot))
