"""Секреты и пути.

Секреты живут в `.env` в корне проекта (режим 600, не версионируется).
Вписывает их пользователь в своём терминале; код только читает файл и
передаёт значения дальше через stdin или переменные окружения — так они не
попадают ни в аргументы команд, ни в onstart-скрипты, которые vast.ai хранит
у себя и показывает в консоли.
"""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_FILE = os.path.join(ROOT, ".env")
DEFAULT_SSH_KEY = os.path.expanduser("~/.ssh/id_ed25519_vast")


def env(name: str, default: str | None = None) -> str | None:
    """Значение из окружения, иначе из .env, иначе default."""
    if os.environ.get(name):
        return os.environ[name]
    for path in (ENV_FILE, os.path.join(ROOT, "tools", ".env")):
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip()
    return default


def require(*names: str) -> dict[str, str]:
    got, missing = {}, []
    for n in names:
        v = env(n)
        (got.setdefault(n, v) if v else missing.append(n))
    if missing:
        raise SystemExit(
            f"не хватает: {', '.join(missing)}.\n"
            f"Впиши их сам, в своём терминале, чтобы они не попали в переписку:\n"
            f"    umask 077\n"
            + "".join(f"    echo '{n}=...' >> {ENV_FILE}\n" for n in missing))
    return got


def ssh_key(path: str | None = None) -> str | None:
    p = path or DEFAULT_SSH_KEY
    return p if os.path.exists(p) else None
