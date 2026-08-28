"""command-line interface."""
from __future__ import annotations

import argparse
import sys

from . import services, style
from .errors import XrayctlError, UsageError
from .output import print_json, print_table
from .qrutil import render_qr

SERVER_COLUMNS = [("#", "number"), ("remarks", "remarks"), ("protocol", "protocol"),
                   ("address", "address"), ("port", "port"), ("ping", "latency_ms")]
SUB_COLUMNS = [("#", "number"), ("title", "title"), ("url", "url"), ("servers", "_count"),
               ("updated", "last_updated")]
ROUTING_COLUMNS = [("#", "number"), ("name", "name"), ("active", "is_active"),
                    ("global", "global_proxy")]


def _server_row(s, number):
    d = s.to_dict()
    d["number"] = number
    return d


def _sub_row(sub, number):
    d = sub.to_dict()
    d["number"] = number
    d["_count"] = len(sub.servers)
    return d




def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                         help="machine-readable output")

    parser = argparse.ArgumentParser(prog="xrayctl", parents=[common],
                                      description="Console proxy utility client (Happ CLI clone).")
    parser.add_argument("--tray", action="store_true", help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command")

    p_server = sub.add_parser("server", parents=[common])
    server_sub = p_server.add_subparsers(dest="server_cmd")

    server_sub.add_parser("list", parents=[common])

    p_add = server_sub.add_parser("add", parents=[common])
    p_add.add_argument("uri", nargs="?", help="vless://, vmess://, trojan://, ss://, socks://, hysteria2://, wireguard://, or happ:// link")
    p_add.add_argument("--file", help="import from a file (link/subscription blob/wg-quote conf)")
    p_add.add_argument("--json-file", dest="json_file", help="import a raw Xray outbound JSON file")

    server_sub.add_parser("import-clipboard", parents=[common])

    p_show = server_sub.add_parser("show", parents=[common])
    p_show.add_argument("id")

    p_rename = server_sub.add_parser("rename", parents=[common])
    p_rename.add_argument("id")
    p_rename.add_argument("name")

    p_remove = server_sub.add_parser("remove", parents=[common])
    p_remove.add_argument("id")

    p_export = server_sub.add_parser("export", parents=[common])
    p_export.add_argument("id")

    p_sub = sub.add_parser("sub", parents=[common])
    sub_sub = p_sub.add_subparsers(dest="sub_cmd")

    sub_sub.add_parser("list", parents=[common])

    p_sub_add = sub_sub.add_parser("add", parents=[common])
    p_sub_add.add_argument("url")

    p_sub_update = sub_sub.add_parser("update", parents=[common])
    p_sub_update.add_argument("id", nargs="?")
    p_sub_update.add_argument("--all", action="store_true")

    p_sub_info = sub_sub.add_parser("info", parents=[common])
    p_sub_info.add_argument("id")

    p_sub_remove = sub_sub.add_parser("remove", parents=[common])
    p_sub_remove.add_argument("id")

    p_connect = sub.add_parser("connect", parents=[common])
    p_connect.add_argument("server_id", nargs="?")

    sub.add_parser("disconnect", parents=[common])
    sub.add_parser("status", parents=[common])

    p_mode = sub.add_parser("mode", parents=[common])
    p_mode.add_argument("mode", choices=["proxy", "tun"])

    p_use = sub.add_parser("use", parents=[common])
    p_use.add_argument("server_id")

    p_ping = sub.add_parser("ping", parents=[common])
    p_ping.add_argument("id", nargs="?")
    p_ping.add_argument("--all", action="store_true")

    sub.add_parser("best", parents=[common])

    p_routing = sub.add_parser("routing", parents=[common])
    routing_sub = p_routing.add_subparsers(dest="routing_cmd")

    routing_sub.add_parser("list", parents=[common])

    p_routing_add = routing_sub.add_parser("add", parents=[common])
    p_routing_add.add_argument("link")

    p_routing_use = routing_sub.add_parser("use", parents=[common])
    p_routing_use.add_argument("id")

    routing_sub.add_parser("off", parents=[common])

    p_config = sub.add_parser("config", parents=[common])
    config_sub = p_config.add_subparsers(dest="config_cmd")

    p_config_set = config_sub.add_parser("set", parents=[common])
    p_config_set.add_argument("key")
    p_config_set.add_argument("value")

    p_config_get = config_sub.add_parser("get", parents=[common])
    p_config_get.add_argument("key", nargs="?")

    p_logs = sub.add_parser("logs", parents=[common])
    p_logs.add_argument("-f", "--follow", action="store_true")

    p_qr = sub.add_parser("qr", parents=[common])
    p_qr.add_argument("id")

    p_core = sub.add_parser("core", parents=[common])
    core_sub = p_core.add_subparsers(dest="core_cmd")
    p_core_install = core_sub.add_parser("install", parents=[common])
    p_core_install.add_argument("--core-type", dest="core_type", choices=["xray", "singbox"],
                                 help="defaults to the configured core_type")
    p_core_install.add_argument("-y", "--yes", action="store_true",
                                 help="skip the confirmation prompt")

    p_startup = sub.add_parser("startup", parents=[common])
    p_startup.add_argument("action", nargs="?", choices=["on", "off", "status"], default=None)

    sub.add_parser("hide", parents=[common])

    return parser




def dispatch(args: argparse.Namespace) -> int:
    as_json = getattr(args, "json", False)

    if getattr(args, "tray", False):
        from .tray import run_tray
        return run_tray(connect_last=True, hide_console=True)

    if args.command == "server":
        return _dispatch_server(args, as_json)
    if args.command == "sub":
        return _dispatch_sub(args, as_json)
    if args.command == "connect":
        state = services.connect(args.server_id)
        if as_json:
            print_json(state)
        else:
            print(style.ok(f"connected (pid {state['pid']})"))
        return 0
    if args.command == "disconnect":
        services.disconnect()
        if as_json:
            print_json({"disconnected": True})
        else:
            print(style.ok("disconnected"))
        return 0
    if args.command == "status":
        st = services.connection_status()
        if as_json:
            print_json(st)
        elif st.get("connected"):
            print(style.ok(f"connected: {st.get('server_remarks', st.get('server_id'))} ({st.get('mode')})"))
        else:
            print(style.info("not connected"))
        return 0
    if args.command == "mode":
        settings = services.set_mode(args.mode)
        _emit(settings.to_dict(), as_json)
        return 0
    if args.command == "use":
        server = services.use_server(args.server_id)
        _emit(server.to_dict(), as_json)
        return 0
    if args.command == "ping":
        return _dispatch_ping(args, as_json)
    if args.command == "best":
        best = services.pick_best()
        if not best:
            print(style.err("no servers have been pinged yet — run `xrayctl ping --all` first"))
            return 3
        if as_json:
            print_json(best.to_dict())
        else:
            print(style.ok(f"now active: {best.remarks} ({best.latency_ms} ms)"))
        return 0
    if args.command == "routing":
        return _dispatch_routing(args, as_json)
    if args.command == "config":
        return _dispatch_config(args, as_json)
    if args.command == "logs":
        return _dispatch_logs(args)
    if args.command == "qr":
        return _dispatch_qr(args)
    if args.command == "core":
        return _dispatch_core(args, as_json)
    if args.command == "startup":
        return _dispatch_startup(args, as_json)
    if args.command == "hide":
        from .tray import run_tray
        return run_tray(connect_last=False, hide_console=True)

    raise UsageError("no command given — run `xrayctl --help`")


def _emit(data, as_json: bool) -> None:
    if as_json:
        print_json(data)
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                print(f"{k}: {v}")
        else:
            print(data)


def _dispatch_server(args, as_json) -> int:
    cmd = args.server_cmd
    if cmd == "list" or cmd is None:
        servers = services.list_servers()
        if as_json:
            print_json([s.to_dict() for s in servers])
        else:
            print_table([_server_row(s, number) for number, s in enumerate(servers, 1)], SERVER_COLUMNS)
        return 0
    if cmd == "add":
        if sum(bool(x) for x in (args.uri, args.file, args.json_file)) != 1:
            raise UsageError("provide exactly one of: <uri>, --file, --json-file")
        if args.uri:
            server = services.add_server_from_uri(args.uri)
            print_json(server.to_dict()) if as_json else print(style.ok("server added"))
        elif args.file:
            servers = services.add_server_from_file(args.file)
            _emit([s.to_dict() for s in servers] if as_json else f"imported {len(servers)} server(s)", as_json)
        else:
            server = services.add_server_from_json_file(args.json_file)
            _emit(server.to_dict(), as_json)
        return 0
    if cmd == "import-clipboard":
        servers = services.import_clipboard()
        _emit([s.to_dict() for s in servers] if as_json else f"imported {len(servers)} server(s) from clipboard", as_json)
        return 0
    if cmd == "show":
        _emit(services.get_server(args.id).to_dict(), as_json)
        return 0
    if cmd == "rename":
        _emit(services.rename_server(args.id, args.name).to_dict(), as_json)
        return 0
    if cmd == "remove":
        services.remove_server(args.id)
        _emit({"removed": args.id}, as_json)
        return 0
    if cmd == "export":
        print(services.export_server(args.id))
        return 0
    raise UsageError("usage: xrayctl server <list|add|import-clipboard|show|rename|remove|export>")


def _dispatch_sub(args, as_json) -> int:
    cmd = args.sub_cmd
    if cmd == "list" or cmd is None:
        subs = services.list_subscriptions()
        if as_json:
            print_json([s.to_dict() for s in subs])
        else:
            print_table([_sub_row(s, number) for number, s in enumerate(subs, 1)], SUB_COLUMNS)
        return 0
    if cmd == "add":
        sub_obj = services.add_subscription(args.url)
        print_json(sub_obj.to_dict()) if as_json else print(style.ok("subscription added"))
        return 0
    if cmd == "update":
        if not args.id and not args.all:
            raise UsageError("usage: xrayctl sub update <id> | --all")
        if args.all:
            updated = services.update_all_subscriptions()
            _emit([s.to_dict() for s in updated] if as_json else f"updated {len(updated)} subscription(s)", as_json)
        else:
            _emit(services.update_subscription(args.id).to_dict(), as_json)
        return 0
    if cmd == "info":
        _emit(services.get_subscription(args.id).to_dict(), as_json)
        return 0
    if cmd == "remove":
        services.remove_subscription(args.id)
        _emit({"removed": args.id}, as_json)
        return 0
    raise UsageError("usage: xrayctl sub <list|add|update|info|remove>")


def _dispatch_ping(args, as_json) -> int:
    if args.all:
        results = services.ping_all_servers()
        if as_json:
            print_json(results)
        else:
            numbers = {server.id: number for number, server in enumerate(services.list_servers(), 1)}
            for sid, ms in results.items():
                label = numbers.get(sid, sid[:8])
                print(style.info(f"{label}: {ms} ms") if ms is not None else style.err(f"{label}: no response"))
        return 0
    if not args.id:
        raise UsageError("usage: xrayctl ping <id> | --all")
    latency = services.ping_one(args.id)
    if as_json:
        print_json({"id": args.id, "latency_ms": latency})
    else:
        print(style.info(f"{latency} ms") if latency is not None else style.err("no response"))
    return 0 if latency is not None else 3


def _dispatch_routing(args, as_json) -> int:
    cmd = args.routing_cmd
    if cmd == "list" or cmd is None:
        profiles = services.list_routing_profiles()
        if as_json:
            print_json([p.to_dict() for p in profiles])
        else:
            rows = []
            for number, profile in enumerate(profiles, 1):
                row = profile.to_dict()
                row["number"] = number
                rows.append(row)
            print_table(rows, ROUTING_COLUMNS)
        return 0
    if cmd == "add":
        profile = services.import_routing_link(args.link)
        if profile is None:
            _emit({"routing": "off"}, as_json)
        else:
            _emit(profile.to_dict(), as_json)
        return 0
    if cmd == "use":
        _emit(services.use_routing_profile(args.id).to_dict(), as_json)
        return 0
    if cmd == "off":
        services.routing_off()
        _emit({"routing": "off"}, as_json)
        return 0
    raise UsageError("usage: xrayctl routing <list|add|use|off>")


def _dispatch_config(args, as_json) -> int:
    cmd = args.config_cmd
    if cmd == "set":
        _emit(services.config_set(args.key, args.value).to_dict(), as_json)
        return 0
    if cmd == "get" or cmd is None:
        _emit(services.config_get(getattr(args, "key", None)), as_json)
        return 0
    raise UsageError("usage: xrayctl config <set|get>")


def _dispatch_logs(args) -> int:
    if args.follow:
        try:
            from . import core
            for line in core.follow_logs():
                print(line)
        except KeyboardInterrupt:
            pass
        return 0
    from . import core
    print(core.read_logs())
    return 0


def _dispatch_qr(args) -> int:
    uri = services.export_server(args.id)
    art = render_qr(uri)
    if art:
        print(art)
    else:
        print("(install the optional 'qrcode' package for a scannable QR: pip install qrcode)")
        print(uri)
    return 0


def _dispatch_core(args, as_json) -> int:
    cmd = args.core_cmd
    if cmd == "install" or cmd is None:
        return _dispatch_core_install(args, as_json)
    raise UsageError("usage: xrayctl core install")


def _dispatch_core_install(args, as_json) -> int:
    from . import install as installer
    core_type = args.core_type or services.get_settings().core_type
    plan = installer.plan_install(core_type)
    size_mb = plan["size_bytes"] / (1024 * 1024)
    print("About to download:")
    print(f"  repo:  {plan['repo']}  ({plan['version']})")
    print(f"  asset: {plan['asset_name']}  (~{size_mb:.1f} MB)")
    print(f"  url:   {plan['url']}")
    if not args.yes:
        answer = input("Proceed with download? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print(style.info("cancelled"))
            return 0
    path = installer.perform_install(plan)
    if as_json:
        print_json({"installed": path, "core_type": core_type})
    else:
        print(style.ok(f"installed: {path}"))
    return 0


def _dispatch_startup(args, as_json) -> int:
    from . import startup

    if args.action is None:
        args.action = "off" if startup.status()["enabled"] else "on"
    if args.action == "on":
        result = {"enabled": True, "command": startup.enable()}
        if not as_json:
            print(style.ok("startup enabled"))
            return 0
    elif args.action == "off":
        result = {"enabled": False, "removed": startup.disable()}
        if not as_json:
            print(style.ok("startup disabled"))
            return 0
    else:
        result = startup.status()
        if not as_json:
            print(style.ok("startup enabled") if result["enabled"] else style.info("startup disabled"))
            return 0
    print_json(result)
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command and not getattr(args, "tray", False):
        from . import interactive
        return interactive.run()
    try:
        return dispatch(args)
    except XrayctlError as e:
        print(style.err(str(e), stream=sys.stderr), file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        print()
        return 130
    except Exception as e:
        print(style.err(f"unexpected error ({type(e).__name__}): {e}", stream=sys.stderr), file=sys.stderr)
        return 1
