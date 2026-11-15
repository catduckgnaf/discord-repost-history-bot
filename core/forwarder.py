"""Logic for forwarding a single message, including attachments, through a webhook."""
from __future__ import annotations

import logging

import discord

from core.config import WEBHOOK_NAME

log = logging.getLogger("feverdream.forwarder")

# Webhook cache keyed by channel ID, so the API is not queried for every
# forwarded message.
_webhook_cache: dict[int, discord.Webhook] = {}


async def get_or_create_webhook(channel: discord.TextChannel) -> discord.Webhook:
    cached = _webhook_cache.get(channel.id)
    if cached is not None:
        return cached

    webhooks = await channel.webhooks()
    webhook = discord.utils.get(webhooks, name=WEBHOOK_NAME)
    if webhook is None:
        webhook = await channel.create_webhook(name=WEBHOOK_NAME)

    _webhook_cache[channel.id] = webhook
    return webhook


def is_forwardable(message: discord.Message) -> bool:
    """A message is forwarded if it has text, an embed or an attachment."""
    return bool(message.content or message.embeds or message.attachments)


def is_new_since_link(message: discord.Message, link_created_at: float) -> bool:
    """Live forwarding only handles messages posted after the link was created.

    Gateway events only deliver new messages, so this is a safety net that
    guarantees history is never copied by the live path.
    """
    return message.created_at.timestamp() >= link_created_at


async def forward_message(message: discord.Message, target_channel: discord.TextChannel) -> int:
    """Forward one message (text, photo, video, embed) to the target channel.

    Returns the number of attachments (files) forwarded successfully.
    """
    webhook = await get_or_create_webhook(target_channel)

    files = []
    for attachment in message.attachments:
        try:
            files.append(await attachment.to_file())
        except discord.HTTPException:
            log.warning("Could not download attachment %s from message %s", attachment.filename, message.id)

    try:
        await webhook.send(
            content=message.content or None,
            username=message.author.display_name[:80] or "FeverDream",
            avatar_url=message.author.display_avatar.url,
            embeds=message.embeds,
            files=files,
            allowed_mentions=discord.AllowedMentions.none(),
            thread=target_channel if isinstance(target_channel, discord.Thread) else discord.utils.MISSING,
        )
    except discord.HTTPException as exc:
        # Most common cause: attachments are too large for the target server
        # (file size limit). Try again without attachments so the text is not lost.
        log.warning("Sending with files failed (%s), retrying without attachments", exc)
        if files:
            await webhook.send(
                content=(message.content or "") + "\n*(attachments could not be forwarded - they are too large)*",
                username=message.author.display_name[:80] or "FeverDream",
                avatar_url=message.author.display_avatar.url,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            raise

    return len(files)
