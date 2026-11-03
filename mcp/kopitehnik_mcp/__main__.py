"""MCP stdio bridge to a locally installed KopiTehnik Print (Windows).

The MCP protocol itself is spoken by the app's own agent
(``PhotoCropAgent.exe mcp``). This package only locates that binary and hands
it the inherited stdin/stdout, so the wrapper stays one tiny, dependency-free
hop and never touches the protocol stream itself (nothing is ever printed to
stdout from here - diagnostics go to stderr).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

APP_DIR_NAMES = ("KopiTehnik Print", "KopiTehnik-Print", "PhotoCrop")
EXE_NAMES = ("PhotoCropAgent.exe", "PhotoCropAgent")
ENV_EXE = "KOPITEHNIK_AGENT_EXE"
ENV_HOME = "KOPITEHNIK_HOME"
INSTALL_URL = "https://github.com/ildargiv/KopiTehnik-Print/releases/latest"

USAGE = """\
kopitehnik-mcp - MCP stdio bridge for KopiTehnik Print (Windows)

Usage:
  kopitehnik-mcp               start the MCP server (same as: PhotoCropAgent.exe mcp)
  kopitehnik-mcp --where       show which agent binary would be started
  kopitehnik-mcp --help        show this message

Environment:
  KOPITEHNIK_AGENT_EXE         full path to PhotoCropAgent.exe (or .py) if the app
                               is installed in a non-standard folder
  KOPITEHNIK_HOME              path to a source checkout (uses photo_crop.py)
"""


class AgentNotFound(RuntimeError):
    """The KopiTehnik Print agent binary could not be located."""


def _install_dirs() -> List[Path]:
    """Candidate install folders, most likely first, de-duplicated."""
    dirs: List[Path] = []

    def add(path: Path) -> None:
        try:
            resolved = path.expanduser()
        except RuntimeError:
            return
        if resolved not in dirs:
            dirs.append(resolved)

    for var in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMW6432", "PROGRAMFILES(X86)", "APPDATA"):
        base = os.environ.get(var)
        if not base:
            continue
        for name in APP_DIR_NAMES:
            add(Path(base) / "Programs" / name)
            add(Path(base) / name)

    for path in _dirs_from_registry():
        add(path)
    return dirs


def _dirs_from_registry() -> List[Path]:
    """InstallLocation of a KopiTehnik entry in Add/Remove Programs, if any."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return []

    locations: List[Path] = []
    roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, key_path in roots:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                count = winreg.QueryInfoKey(key)[0]
                for index in range(count):
                    try:
                        sub_name = winreg.EnumKey(key, index)
                        with winreg.OpenKey(key, sub_name) as sub:
                            display = _reg_value(sub, "DisplayName") or ""
                            if "kopitehnik" not in display.lower():
                                continue
                            location = _reg_value(sub, "InstallLocation")
                            if location:
                                locations.append(Path(location))
                    except OSError:
                        continue
        except OSError:
            continue
    return locations


def _reg_value(key, name: str) -> Optional[str]:
    import winreg

    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return value if isinstance(value, str) else None


def _source_checkout() -> Optional[Path]:
    for root in (os.environ.get(ENV_HOME), os.getcwd()):
        if not root:
            continue
        candidate = Path(root) / "photo_crop.py"
        if candidate.is_file():
            return candidate
    return None


def _cmd_for(path: Path) -> List[str]:
    if path.suffix.lower() == ".py":
        return [sys.executable, str(path)]
    return [str(path)]


def resolve_agent() -> List[str]:
    """Return the command that starts the KopiTehnik Print MCP agent."""
    override = os.environ.get(ENV_EXE)
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise AgentNotFound("%s points to %s, which does not exist" % (ENV_EXE, path))
        return _cmd_for(path)

    found = shutil.which("PhotoCropAgent.exe") or shutil.which("PhotoCropAgent")
    if found:
        return _cmd_for(Path(found))

    for directory in _install_dirs():
        for exe in EXE_NAMES:
            candidate = directory / exe
            if candidate.is_file():
                return _cmd_for(candidate)

    source = _source_checkout()
    if source is not None:
        return _cmd_for(source)

    raise AgentNotFound(
        "KopiTehnik Print was not found on this PC.\n"
        "Install it first: %s\n"
        "Already installed elsewhere? Set %s to the full path of PhotoCropAgent.exe."
        % (INSTALL_URL, ENV_EXE)
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0

    if args and args[0] in ("--where", "--print-command"):
        try:
            command = resolve_agent()
        except AgentNotFound as exc:
            sys.stderr.write("%s\n" % exc)
            return 3
        sys.stdout.write(" ".join('"%s"' % part if " " in part else part for part in command) + "\n")
        return 0

    if args and args[0].startswith("-"):
        sys.stderr.write("Unknown option: %s\n\n%s" % (args[0], USAGE))
        return 2

    try:
        command = resolve_agent()
    except AgentNotFound as exc:
        sys.stderr.write("%s\n" % exc)
        return 3

    if os.name != "nt":
        sys.stderr.write("Note: KopiTehnik Print runs on Windows; starting the agent anyway.\n")

    try:
        return subprocess.call(command + (args or ["mcp"]))
    except KeyboardInterrupt:
        return 130
    except OSError as exc:
        sys.stderr.write("Failed to start %s: %s\n" % (command[0], exc))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
