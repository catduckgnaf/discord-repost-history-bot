"""Commands for managing live channel links (source -> target)."""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from bot import FeverDreamBot


class LinkingCog(commands.Cog):
    def __init__(self, bot: "FeverDreamBot") -> None:
        self.bot = bot

    def _resolve_channel(self, channel_id: int) -> discord.TextChannel | None:
        channel = self.bot.get_channel(channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    @app_commands.command(
        name="link-add",
        description="Start live forwarding of new messages from a source channel to a target channel.",
    )
    @app_commands.describe(
        source="Source channel (on this server) to forward new messages from.",
        target_channel_id="Target channel ID (can be on another server where the bot is a member).",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def link_add(
        self,
        interaction: discord.Interaction,
        source: discord.TextChannel,
        target_channel_id: str,
    ) -> None:
        try:
            target_id = int(target_channel_id.strip())
        except ValueError:
            await interaction.response.send_message("The target channel ID must be a number.", ephemeral=True)
            return

        target = self._resolve_channel(target_id)
        if target is None:
            await interaction.response.send_message(
                "Target channel not found - the bot must be a member of that server and have the Manage Webhooks permission.",
                ephemeral=True,
            )
            return

        link = await self.bot.link_storage.add_link(
            source_channel_id=source.id,
            target_channel_id=target.id,
            source_guild_id=source.guild.id,
            target_guild_id=target.guild.id,
            created_by=interaction.user.id,
        )
        await interaction.response.send_message(
            f"Link **{link.id}** created: {source.mention} ({source.guild.name}) "
            f"-> #{target.name} ({target.guild.name}). Only new messages posted from now on will be forwarded; "
            f"existing history is not copied.",
        )

    @app_commands.command(
        name="link-remove",
        description="Stop live forwarding from the given source channel.",
    )
    @app_commands.describe(source="Source channel to stop forwarding from.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def link_remove(self, interaction: discord.Interaction, source: discord.TextChannel) -> None:
        removed = await self.bot.link_storage.remove_link(source.id)
        if removed:
            await interaction.response.send_message(f"Link from {source.mention} removed.")
        else:
            await interaction.response.send_message(
                f"No link exists for {source.mention}.", ephemeral=True
            )

    @app_commands.command(name="link-list", description="List the active channel links for this server.")
    async def link_list(self, interaction: discord.Interaction) -> None:
        links = self.bot.link_storage.links_for_guild(interaction.guild_id)
        if not links:
            await interaction.response.send_message("No links are active.", ephemeral=True)
            return

        lines = []
        for link in links:
            source = self.bot.get_channel(link.source_channel_id)
            target = self.bot.get_channel(link.target_channel_id)
            source_name = source.mention if source else f"#{link.source_channel_id}"
            target_name = f"#{target.name}" if target else f"#{link.target_channel_id}"
            lines.append(f"`{link.id}` {source_name} -> {target_name}")

        await interaction.response.send_message("**Active links:**\n" + "\n".join(lines))

    @link_add.error
    @link_remove.error
    async def on_permission_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You need the **Manage Guild** permission to use this command.", ephemeral=True
            )
        else:
            raise error


async def setup(bot: "FeverDreamBot") -> None:
    await bot.add_cog(LinkingCog(bot))
