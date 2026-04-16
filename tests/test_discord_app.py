from __future__ import annotations

from dataclasses import dataclass, field

from jarvis.apps.discord.discord_app import DiscordApp
from jarvis.apps.discord.discord_context import DiscordContext
from jarvis.enums.action_type import ActionType
from jarvis.models.command import Command


@dataclass
class FakeDiscordController:
    running: bool = True
    focused: bool = False
    launched: bool = False
    closed: bool = False
    quick_switcher_calls: list[str] = field(default_factory=list)
    typed: list[str] = field(default_factory=list)
    enters: int = 0
    mutes: int = 0
    deafens: int = 0
    previouses: int = 0

    def is_running(self) -> bool:
        return self.running

    def launch(self) -> bool:
        self.launched = True
        self.running = True
        self.focused = True
        return True

    def close(self) -> bool:
        self.closed = True
        self.running = False
        return True

    def focus_window(self) -> bool:
        self.focused = self.running
        return self.focused

    def quick_switcher(self, query: str) -> bool:
        self.quick_switcher_calls.append(query)
        return True

    def type_text(self, text: str) -> None:
        self.typed.append(text)

    def press_enter(self) -> None:
        self.enters += 1

    def hotkey_toggle_mute(self) -> None:
        self.mutes += 1

    def hotkey_toggle_deafen(self) -> None:
        self.deafens += 1

    def hotkey_previous_channel(self) -> None:
        self.previouses += 1


def _make_app(running: bool = True) -> tuple[DiscordApp, FakeDiscordController]:
    controller = FakeDiscordController(running=running)
    app = DiscordApp(controller=controller)
    return app, controller


def test_discord_app_opens_dm_and_remembers_user() -> None:
    app, controller = _make_app()
    cmd = Command(
        action=ActionType.DISCORD_OPEN_DM,
        target="",
        parameters={"target_name": "Renan"},
    )
    result = app.execute(cmd)

    assert result.success is True
    assert controller.quick_switcher_calls == ["Renan"]
    assert app.context.current_dm == "Renan"
    assert app.context.last_user_mentioned == "Renan"


def test_discord_app_sends_dm_message_via_quick_switcher() -> None:
    app, controller = _make_app()
    cmd = Command(
        action=ActionType.DISCORD_SEND_MESSAGE,
        target="",
        parameters={"target_type": "dm", "target_name": "Renan", "message": "Oi, já volto."},
    )
    result = app.execute(cmd)

    assert result.success is True
    assert controller.quick_switcher_calls == ["Renan"]
    assert controller.typed == ["Oi, já volto."]
    assert controller.enters == 1
    assert app.context.current_dm == "Renan"


def test_discord_app_send_message_uses_context_when_recipient_missing() -> None:
    app, controller = _make_app()
    app.context.last_user_mentioned = "Eduardo"

    cmd = Command(
        action=ActionType.DISCORD_SEND_MESSAGE,
        target="",
        parameters={"target_type": "dm", "target_name": "", "message": "fala que ja vou"},
    )
    result = app.execute(cmd)

    assert result.success is True
    assert controller.quick_switcher_calls == ["Eduardo"]
    assert controller.typed == ["fala que ja vou"]


def test_discord_app_opens_channel_with_hash_prefix() -> None:
    app, controller = _make_app()
    cmd = Command(
        action=ActionType.DISCORD_OPEN_CHANNEL,
        target="",
        parameters={"channel_name": "geral", "server_name": "Faculdade"},
    )
    result = app.execute(cmd)

    assert result.success is True
    assert controller.quick_switcher_calls == ["#geral"]
    assert app.context.current_channel == "geral"
    assert app.context.current_server == "Faculdade"


def test_discord_app_toggle_mute_and_deafen() -> None:
    app, controller = _make_app()
    assert app.execute(Command(action=ActionType.DISCORD_TOGGLE_MUTE, target="")).success is True
    assert app.execute(Command(action=ActionType.DISCORD_TOGGLE_DEAFEN, target="")).success is True
    assert controller.mutes == 1
    assert controller.deafens == 1


def test_discord_app_join_voice_remembers_voice_channel() -> None:
    app, controller = _make_app()
    cmd = Command(
        action=ActionType.DISCORD_JOIN_VOICE,
        target="",
        parameters={"channel_name": "amigos"},
    )
    result = app.execute(cmd)

    assert result.success is True
    assert controller.quick_switcher_calls == ["#amigos"]
    assert app.context.current_voice_channel == "amigos"


def test_discord_app_set_status_returns_not_implemented() -> None:
    app, _ = _make_app()
    result = app.execute(
        Command(
            action=ActionType.DISCORD_SET_STATUS,
            target="",
            parameters={"status": "dnd", "custom_text": "Estudando agora"},
        )
    )
    assert result.success is False
    assert "not yet implemented" in result.message.lower()


def test_discord_app_reply_current_requires_remembered_target() -> None:
    app, controller = _make_app()
    no_context = app.execute(
        Command(action=ActionType.DISCORD_REPLY_CURRENT, target="", parameters={"message": "ok"})
    )
    assert no_context.success is False

    app.context.current_dm = "Renan"
    ok = app.execute(
        Command(action=ActionType.DISCORD_REPLY_CURRENT, target="", parameters={"message": "ja vou"})
    )
    assert ok.success is True
    assert controller.typed == ["ja vou"]
    assert controller.enters == 1
