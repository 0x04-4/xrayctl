"""proxy core installer."""
from __future__ import annotations

import io
import json
import platform
import shutil
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from . import storage
from .errors import CoreError, NetworkError

GITHUB_REPOS = {
    "xray": "XTLS/Xray-core",
    "singbox": "SagerNet/sing-box",
}

_BINARY_BASENAME = {
    "xray": "xray",
    "singbox": "sing-box",
}


def _api_latest_release(repo: str) -> dict:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url, headers={"User-Agent": "xrayctl", "Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise NetworkError(f"failed to query releases for {repo}: {e}")


def _detect_os_arch():
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        arch = "amd64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = machine
    return system, arch


def _pick_asset(assets: list, core_type: str, system: str, arch: str):
    os_key = "macos" if (core_type == "xray" and system == "darwin") else system
    candidates = []
    for a in assets:
        name = a["name"].lower()
        if not (name.endswith(".zip") or name.endswith(".tar.gz")):
            continue
        if os_key not in name:
            continue
        if core_type == "xray":
            arch_ok = ("64" in name and "arm" not in name) if arch == "amd64" else ("arm64" in name)
        else:
            arch_ok = arch in name
        if arch_ok:
            candidates.append(a)
    if not candidates:
        return None
    candidates.sort(key=lambda a: len(a["name"]))
    return candidates[0]


def plan_install(core_type: str) -> dict:
    """Resolves exactly what would be downloaded, WITHOUT downloading it."""
    if core_type not in GITHUB_REPOS:
        raise CoreError(f"unknown core_type: {core_type!r} (expected 'xray' or 'singbox')")
    repo = GITHUB_REPOS[core_type]
    release = _api_latest_release(repo)
    system, arch = _detect_os_arch()
    asset = _pick_asset(release.get("assets", []), core_type, system, arch)
    if not asset:
        available = ", ".join(a["name"] for a in release.get("assets", [])) or "(none listed)"
        raise CoreError(
            f"couldn't find a {system}/{arch} build in {repo} release "
            f"{release.get('tag_name', '?')}. Available assets: {available}. "
            f"Install manually from https://github.com/{repo}/releases/latest"
        )
    return {
        "core_type": core_type,
        "repo": repo,
        "version": release.get("tag_name", "?"),
        "asset_name": asset["name"],
        "url": asset["browser_download_url"],
        "size_bytes": asset.get("size", 0),
    }


def _find_member(names: list, basename: str):
    wanted = {basename, basename + ".exe"}
    for n in names:
        base = n.rsplit("/", 1)[-1]
        if base in wanted:
            return n
    return None


def perform_install(plan: dict) -> str:
    """Downloads + extracts per `plan` (from plan_install), points settings.core_path
    at the result, and returns the installed binary's path. Only call this after
    the user has explicitly confirmed the plan."""
    core_type = plan["core_type"]
    try:
        req = urllib.request.Request(plan["url"], headers={"User-Agent": "xrayctl"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
    except Exception as e:
        raise NetworkError(f"download failed: {e}")

    install_dir = storage.data_dir() / "bin" / core_type
    install_dir.mkdir(parents=True, exist_ok=True)
    basename = _BINARY_BASENAME[core_type]
    exe_name = basename + (".exe" if sys.platform == "win32" else "")
    target = install_dir / exe_name

    asset_name = plan["asset_name"]
    if asset_name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            member = _find_member(zf.namelist(), basename)
            if not member:
                raise CoreError(f"no '{basename}' binary found inside {asset_name}")
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    elif asset_name.endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            member = _find_member(tf.getnames(), basename)
            if not member:
                raise CoreError(f"no '{basename}' binary found inside {asset_name}")
            src = tf.extractfile(member)
            with open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    else:
        raise CoreError(f"unrecognized archive format: {asset_name}")

    if sys.platform != "win32":
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    settings = storage.load_settings()
    settings.core_type = core_type
    settings.core_path = str(target)
    storage.save_settings(settings)
    return str(target)
