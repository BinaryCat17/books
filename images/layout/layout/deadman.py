import os
import threading
import time
import urllib.request


def watch(last_request, idle_s: float) -> None:
    if idle_s <= 0:
        return

    def loop() -> None:
        started = time.time()
        while True:
            time.sleep(30)
            last = last_request() or started
            if time.time() - last > idle_s:
                key, iid = os.environ.get("CONTAINER_API_KEY"), os.environ.get("CONTAINER_ID")
                if key and iid:
                    req = urllib.request.Request(f"https://console.vast.ai/api/v0/instances/{iid}/", method="DELETE",
                                                 headers={"Authorization": f"Bearer {key}"})
                    try:
                        urllib.request.urlopen(req, timeout=30)
                    except Exception:
                        pass
                os._exit(0)

    threading.Thread(target=loop, daemon=True).start()
