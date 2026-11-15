"""Tests for English user-facing text and live-only forwarding."""
from __future__ import annotations

import asyncio
import datetime as dt
import re
from pathlib import Path
from types import SimpleNamespace

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from core import config
from core.forwarder import is_forwardable, is_new_since_link

ROOT = Path(__file__).resolve().parent.parent
CZECH_HINTS = re.compile(
    r"zpr[aá]v|prepos|kan[aá]l|p[rř][ií]kaz|[uú]loh|c[ií]lov|zdroj|propoj|opr[aá]vn|"
    r"[ěščřžýáíéúůďťňĚŠČŘŽÝÁÍÉÚŮĎŤŇ]",
    re.IGNORECASE,
)


def _py_files():
    for path in ROOT.rglob("*.py"):
        if ".venv" in path.parts or "tests" in path.parts:
            continue
        yield path


def test_no_czech_text_in_source():
    offenders = []
    for path in _py_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if CZECH_HINTS.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


class _FakeBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.none(), help_command=None)
        self.link_storage = None
        self.job_manager = None


async def _load(extensions):
    bot = _FakeBot()
    for extension in extensions:
        await bot.load_extension(extension)
    return bot


def _walk(bot):
    return {cmd.name: cmd for cmd in bot.tree.get_commands()}


def test_default_extensions_exclude_history():
    assert config.extensions_for(False) == ("cogs.linking", "cogs.broadcast")
    assert "cogs.repost" in config.extensions_for(True)


def test_history_repost_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_HISTORY_REPOST", raising=False)
    assert config.env_flag("ENABLE_HISTORY_REPOST", False) is False
    assert config.HISTORY_REPOST_ENABLED is False


@pytest.mark.parametrize(
    "raw,expected",
    [("true", True), ("TRUE", True), ("1", True), ("yes", True), ('"true"', True),
     ("false", False), ("0", False), ("", False), ("nonsense", False)],
)
def test_env_flag(monkeypatch, raw, expected):
    monkeypatch.setenv("X_FLAG", raw)
    assert config.env_flag("X_FLAG", False) is expected


def test_live_only_registers_no_history_commands():
    bot = asyncio.run(_load(config.extensions_for(False)))
    names = set(_walk(bot))
    assert names == {"link-add", "link-remove", "link-list", "broadcast"}


def test_history_commands_available_when_enabled():
    bot = asyncio.run(_load(config.extensions_for(True)))
    names = set(_walk(bot))
    assert {"repost-history", "repost-status", "repost-stop"} <= names


def test_all_command_text_is_english_ascii():
    bot = asyncio.run(_load(config.extensions_for(True)))
    for name, cmd in _walk(bot).items():
        assert cmd.description.isascii(), (name, cmd.description)
        assert not CZECH_HINTS.search(cmd.description), (name, cmd.description)
        for param in cmd.parameters:
            assert param.description != "…", (name, param.name, "missing description")
            assert param.description.isascii(), (name, param.name, param.description)
            assert not CZECH_HINTS.search(param.description), (name, param.name)


def _msg(created: dt.datetime, content="hi"):
    return SimpleNamespace(content=content, embeds=[], attachments=[], created_at=created)


def test_is_new_since_link_blocks_history():
    link_time = dt.datetime(2026, 11, 14, 12, 0, tzinfo=dt.timezone.utc)
    old = _msg(link_time - dt.timedelta(seconds=1))
    new = _msg(link_time + dt.timedelta(seconds=1))
    assert is_new_since_link(old, link_time.timestamp()) is False
    assert is_new_since_link(new, link_time.timestamp()) is True


def test_is_forwardable():
    now = dt.datetime.now(dt.timezone.utc)
    assert is_forwardable(_msg(now, "text"))
    assert not is_forwardable(_msg(now, ""))


def test_on_message_skips_pre_link_messages(monkeypatch, tmp_path):
    import bot as bot_module
    from core.storage import ChannelLink, LinkStorage

    storage = LinkStorage(path=tmp_path / "links.json")
    link_time = dt.datetime(2026, 11, 14, 12, 0, tzinfo=dt.timezone.utc)
    storage._links["l1"] = ChannelLink("l1", 10, 20, 1, 2, 3, link_time.timestamp())

    forwarded = []

    async def fake_forward(message, target):
        forwarded.append(message)
        return 0

    monkeypatch.setattr(bot_module, "forward_message", fake_forward)

    fake_bot = SimpleNamespace(
        user=object(),
        link_storage=storage,
        get_channel=lambda cid: object(),
        process_commands=lambda m: asyncio.sleep(0),
    )

    def make(created):
        return SimpleNamespace(
            author=object(), webhook_id=None, channel=SimpleNamespace(id=10),
            content="x", embeds=[], attachments=[], created_at=created, id=1,
        )

    old = make(link_time - dt.timedelta(hours=1))
    new = make(link_time + dt.timedelta(hours=1))
    asyncio.run(bot_module.FeverDreamBot.on_message(fake_bot, old))
    asyncio.run(bot_module.FeverDreamBot.on_message(fake_bot, new))
    assert forwarded == [new]
