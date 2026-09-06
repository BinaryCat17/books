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
    # Один путь, а не два. Запасной `tools/.env` держал в живых расхождение
    # трёх мест: образец учил класть в `tools/.env`, шапка этого файла
    # говорила «в корне», а третье место называло свой. Пока запасной путь
    # работал, расхождение никого не било и потому не чинилось.
    for path in (ENV_FILE,):
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip()
    return default
def ssh_key(path: str | None = None) -> str | None:
    p = path or DEFAULT_SSH_KEY
    return p if os.path.exists(p) else None
