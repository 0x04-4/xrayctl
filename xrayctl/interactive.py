"""interactive command prompt."""
from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass

from . import services, storage, style
from .errors import XrayctlError

try:
    from prompt_toolkit.completion import Completer
except ImportError:
    class Completer:
        pass


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    aliases: tuple[str, ...] = ()


COMMANDS = (
    Command("help", "show commands", ("h", "?")),
    Command("list", "list servers", ("servers", "server", "ls")),
    Command("sub", "list/manage subscriptions", ("subs", "subscriptions")),
    Command("add", "add a subscription <url>"),
    Command("update", "update subscriptions", ("refresh", "reload")),
    Command("connect", "connect [server id]"),
    Command("disconnect", "disconnect"),
    Command("status", "show connection status", ("info",)),
    Command("ping", "ping all or one server"),
    Command("settings", "show or set configuration", ("config",)),
    Command("logs", "show logs or follow with -f"),
    Command("startup", "enable/disable tray autostart"),
    Command("hide", "hide this window to the tray"),
    Command("hwid", "show the current subscription hwid"),
    Command("exit", "leave xrayctl", ("quit", "q")),
)

_CLI_COMMANDS = {
    "server", "sub", "connect", "disconnect", "status", "mode", "use",
    "ping", "best", "routing", "config", "logs", "qr", "core", "startup", "hide",
}


def _fuzzy_score(query: str, candidate: str):
    """Return a sort key for subsequence matches, or None when unmatched."""
    query, candidate = query.lower(), candidate.lower()
    if not query:
        return (0, 0, 0)
    if query in candidate:
        return (0, candidate.index(query), len(candidate))
    position = -1
    gaps = 0
    for char in query:
        found = candidate.find(char, position + 1)
        if found < 0:
            return None
        gaps += found - position - 1
        position = found
    return (1, gaps, len(candidate))


class SlashCompleter(Completer):
    """prompt_toolkit-compatible completer kept import-free for fallback mode."""

    def get_completions(self, document, complete_event):
        from prompt_toolkit.completion import Completion

        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        query = text[1:]
        matches = []
        for command in COMMANDS:
            score = _fuzzy_score(query, command.name)
            if score is not None:
                aliases = ", ".join(f"/{alias}" for alias in command.aliases)
                description = command.description
                if aliases:
                    description += f" · {aliases}"
                matches.append((score, command, description))
        for _, command, description in sorted(matches, key=lambda item: item[0]):
            yield Completion(
                command.name,
                start_position=-len(query),
                display=f"/{command.name}",
                display_meta=description,
            )


def _split_command(line: str) -> list[str]:
    try:
        tokens = shlex.split(line, posix=False)
    except ValueError as exc:
        raise ValueError(f"invalid command quoting: {exc}") from exc
    return [
        token[1:-1]
        if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'"
        else token
        for token in tokens
    ]


def _command_argv(line: str) -> list[str]:
    """Convert a slash command (or a compatible bare command) to CLI argv."""
    tokens = _split_command(line.strip())
    if not tokens:
        return []
    name = tokens[0].lstrip("/").lower()
    args = tokens[1:]

    if name in ("help", "h", "?"):
        return ["__help__"]
    if name in ("exit", "quit", "q"):
        return ["__exit__"]
    if name == "hwid":
        return ["__hwid__"]
    if name == "hide":
        return ["__hide__"]
    if name in ("list", "servers", "server", "ls"):
        return ["server", *(args or ["list"])]
    if name in ("sub", "subs", "subscriptions"):
        return ["sub", *(args or ["list"])]
    if name == "add":
        return ["sub", "add", *args]
    if name in ("refresh", "update", "reload"):
        return ["sub", "update", *(args or ["--all"])]
    if name in ("status", "info"):
        return ["status", *args]
    if name == "ping" and (not args or args == ["all"]):
        return ["ping", "--all"]
    if name == "settings":
        return ["config", *args]
    if name not in _CLI_COMMANDS:
        raise ValueError(f"unknown command: /{name}; type / for the command menu")
    return [name, *args]


def _print_help() -> None:
    print(f"\n{style.bracket('!')} slash commands")
    for command in COMMANDS:
        aliases = f" ({', '.join('/' + a for a in command.aliases)})" if command.aliases else ""
        print(f"  /{command.name:<10} {command.description}{aliases}")
    print("\ntype / and use ↑/↓ plus tab or enter to choose a command.")
    print("examples: /list, /update, /connect <id>, /add <url>, /startup, /hide")
    print("advanced commands still work: /server, /routing, /qr, /core")


def _print_banner() -> None:
    servers = len(services.list_servers())
    subscriptions = len(services.list_subscriptions())
    state = services.connection_status()
    connection = "connected" if state.get("connected") else "not connected"
    print(f"\n{style.bracket('!')} xrayctl · {servers} servers · {subscriptions} subscriptions · {connection}")
    print("type / to open commands; tab/enter selects, ↑/↓ navigates.")


def _session():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return None
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
    except ImportError:
        return None
    history = storage.data_dir() / "command_history"
    return PromptSession(
        history=FileHistory(str(history)),
        completer=SlashCompleter(),
        complete_while_typing=True,
    )


def _run_command(line: str) -> bool:
    argv = _command_argv(line)
    if not argv:
        return False
    if argv == ["__exit__"]:
        return True
    if argv == ["__help__"]:
        _print_help()
        return False
    if argv == ["__hwid__"]:
        value = storage.device_hwid()
        print(f"hwid: {value} ({len(value)} chars)")
        return False
    if argv == ["__hide__"]:
        from .tray import hide_current
        return bool(hide_current())

    from . import cli
    try:
        cli.main(argv)
    except SystemExit:
        pass
    return False


def run() -> int:
    try:
        _print_banner()
        session = _session()
        while True:
            try:
                line = session.prompt("> ") if session else input("> ")
            except KeyboardInterrupt:
                print()
                continue
            except EOFError:
                print()
                return 0
            if not line.strip():
                continue
            try:
                if _run_command(line):
                    return 0
            except (ValueError, XrayctlError) as exc:
                print(style.err(str(exc)))
    except KeyboardInterrupt:
        print()
        return 130
