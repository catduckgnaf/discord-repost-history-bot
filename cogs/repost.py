"""Commands for bulk history repost plus status messages.

This cog is only loaded when ENABLE_HISTORY_REPOST=true.
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from core.config import PROGRESS_UPDATE_EVERY, SEND_DELAY_SECONDS
from core.forwarder import forward_message, is_forwardable
from core.jobs import RepostJob

if TYPE_CHECKING:
    from bot import FeverDreamBot


def _progress_embed(job: RepostJob, *, title: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Messages processed", value=str(job.processed_messages), inline=True)
    embed.add_field(name="Files forwarded", value=str(job.forwarded_files), inline=True)
    embed.add_field(name="Skipped", value=str(job.skipped_messages), inline=True)
    embed.add_field(name="Elapsed", value=f"{job.duration_seconds:.0f} s", inline=True)
    embed.set_footer(text=f"Job ID: {job.id}")
    return embed


class RepostCog(commands.Cog):
    def __init__(self, bot: "FeverDreamBot") -> None:
        self.bot = bot

    def _resolve_channel(self, channel_id: int) -> discord.TextChannel | None:
        channel = self.bot.get_channel(channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _run_history_job(
        self,
        job: RepostJob,
        source: discord.TextChannel,
        target: discord.TextChannel,
        status_message: discord.Message,
    ) -> None:
        try:
            async for message in source.history(limit=job.limit, oldest_first=True):
                if job.cancel_requested:
                    job.status = "cancelled"
                    break

                if is_forwardable(message):
                    try:
                        job.forwarded_files += await forward_message(message, target)
                    except discord.HTTPException:
                        job.skipped_messages += 1
                else:
                    job.skipped_messages += 1

                job.processed_messages += 1

                if job.processed_messages % PROGRESS_UPDATE_EVERY == 0:
                    try:
                        await status_message.edit(
                            embed=_progress_embed(job, title="⏳ Repost in progress...", color=discord.Color.blurple())
                        )
                    except discord.HTTPException:
                        pass

                await asyncio.sleep(SEND_DELAY_SECONDS)
            else:
                job.status = "done"
        except Exception as exc:  # noqa: BLE001 - report any job error
            job.status = "error"
            job.error_message = str(exc)
        finally:
            job.finished_at = time.time()
            if job.status == "done":
                title, color = "✅ Repost finished - the job is done!", discord.Color.green()
            elif job.status == "cancelled":
                title, color = "🛑 Repost cancelled", discord.Color.orange()
            else:
                title, color = f"❌ Repost failed: {job.error_message}", discord.Color.red()
            try:
                await status_message.edit(embed=_progress_embed(job, title=title, color=color))
            except discord.HTTPException:
                pass

    @app_commands.command(
        name="repost-history",
        description="Repost the whole (or limited) message history of a source channel into a target channel.",
    )
    @app_commands.describe(
        source="Source channel (on this server) whose history you want to repost.",
        target_channel_id="Target channel ID (can be on another server where the bot is a member).",
        limit="How many of the newest messages to repost. Leave empty to repost all messages.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def repost_history(
        self,
        interaction: discord.Interaction,
        source: discord.TextChannel,
        target_channel_id: str,
        limit: app_commands.Range[int, 1, 1_000_000] | None = None,
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

        await interaction.response.defer(thinking=True)

        job = self.bot.job_manager.create(
            guild_id=interaction.guild_id,
            started_by=interaction.user.id,
            source_channel_id=source.id,
            target_channel_id=target.id,
            limit=limit,
        )

        status_message = await interaction.followup.send(
            embed=_progress_embed(job, title="⏳ Repost started...", color=discord.Color.blurple()),
            wait=True,
        )

        job.task = asyncio.create_task(self._run_history_job(job, source, target, status_message))

    @app_commands.command(name="repost-status", description="Show the status of running and recent repost jobs on this server.")
    async def repost_status(self, interaction: discord.Interaction) -> None:
        jobs = self.bot.job_manager.all_jobs_for_guild(interaction.guild_id)
        if not jobs:
            await interaction.response.send_message("No repost job has run here yet.", ephemeral=True)
            return

        lines = []
        for job in jobs[-10:]:
            lines.append(
                f"`{job.id}` [{job.status}] {job.processed_messages} messages, "
                f"{job.forwarded_files} files (source <#{job.source_channel_id}> -> target <#{job.target_channel_id}>)"
            )
        await interaction.response.send_message("**Repost jobs:**\n" + "\n".join(lines), ephemeral=True)

    @app_commands.command(name="repost-stop", description="Stop a running repost job by its ID.")
    @app_commands.describe(job_id="ID of the repost job to stop (see /repost-status).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def repost_stop(self, interaction: discord.Interaction, job_id: str) -> None:
        ok = self.bot.job_manager.request_cancel(job_id)
        if ok:
            await interaction.response.send_message(f"Job `{job_id}` will stop after the current message finishes.")
        else:
            await interaction.response.send_message(f"Job `{job_id}` is not running or does not exist.", ephemeral=True)

    @repost_history.error
    @repost_stop.error
    async def on_permission_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You need the **Manage Guild** permission to use this command.", ephemeral=True
            )
        else:
            raise error


async def setup(bot: "FeverDreamBot") -> None:
    await bot.add_cog(RepostCog(bot))
