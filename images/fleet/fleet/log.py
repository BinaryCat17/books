import time


def log(text: str, **fields: object) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)
