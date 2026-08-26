import pexpect
import json
import time
import threading
import requests


API_URL = "http://localhost:8000/api/v1/data"
TOKEN = "tronn_sec_token_889900"

running = True
batch = []
batch_lock = threading.Lock()


# ============================================================
# API SENDER
# ============================================================

def api_sender():
    global running
    global batch

    while running:
        time.sleep(1)

        with batch_lock:
            events = batch
            batch = []

        if not events:
            print("[API] 0 events", flush=True)
            continue

        payload = {
            "ble": events
        }

        print(
            f"[API] Sending {len(events)} events...",
            flush=True
        )

        try:
            response = requests.post(
                API_URL,
                headers={
                    "token": TOKEN,
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=5
            )

            print(
                f"[API] HTTP {response.status_code}",
                flush=True
            )

            print(
                f"[API] Response: {response.text}",
                flush=True
            )

        except Exception as e:
            print(
                f"[API ERROR] {type(e).__name__}: {e}",
                flush=True
            )


# ============================================================
# MAIN
# ============================================================

def main():

    global running
    global batch

    print(
        "Starting bluetoothctl...",
        flush=True
    )

    # Start bluetoothctl
    child = pexpect.spawn(
        "bluetoothctl",
        encoding="utf-8",
        timeout=1
    )

    # Don't let pexpect automatically print anything
    child.logfile = None

    # --------------------------------------------------------
    # Start API thread
    # --------------------------------------------------------

    api_thread = threading.Thread(
        target=api_sender,
        daemon=True
    )

    api_thread.start()

    # --------------------------------------------------------
    # Start Bluetooth scanning
    # --------------------------------------------------------

    time.sleep(1)

    child.sendline("power on")

    time.sleep(1)

    child.sendline("scan on")

    print(
        "Bluetooth scanning...",
        flush=True
    )

    # --------------------------------------------------------
    # Read bluetoothctl continuously
    # --------------------------------------------------------

    buffer = ""

    try:

        while True:

            try:

                data = child.read_nonblocking(
                    size=4096,
                    timeout=0.2
                )

                if not data:
                    continue

                buffer += data

                # Process complete lines
                while "\n" in buffer:

                    line, buffer = buffer.split(
                        "\n",
                        1
                    )

                    line = line.rstrip("\r")

                    if not line:
                        continue

                    # ------------------------------------------------
                    # PRINT RAW DATA
                    # ------------------------------------------------

                    print(
                        line,
                        flush=True
                    )

                    # ------------------------------------------------
                    # STORE RAW DATA
                    # NO PARSING
                    # ------------------------------------------------

                    with batch_lock:

                        batch.append(line)

            except pexpect.TIMEOUT:

                continue

            except pexpect.EOF:

                print(
                    "[BLE] bluetoothctl exited",
                    flush=True
                )

                break

    except KeyboardInterrupt:

        print(
            "\nStopping...",
            flush=True
        )

    finally:

        running = False

        # --------------------------------------------------------
        # Send remaining events
        # --------------------------------------------------------

        with batch_lock:

            remaining = batch.copy()

            batch.clear()

        if remaining:

            print(
                f"[API] Sending final {len(remaining)} events...",
                flush=True
            )

            try:

                response = requests.post(
                    API_URL,
                    headers={
                        "token": TOKEN,
                        "Content-Type": "application/json"
                    },
                    json={
                        "ble": remaining
                    },
                    timeout=5
                )

                print(
                    f"[API] Final HTTP {response.status_code}",
                    flush=True
                )

                print(
                    f"[API] Final Response: {response.text}",
                    flush=True
                )

            except Exception as e:

                print(
                    f"[API ERROR] {type(e).__name__}: {e}",
                    flush=True
                )

        # --------------------------------------------------------
        # Stop bluetoothctl
        # --------------------------------------------------------

        try:

            child.sendline("scan off")

            time.sleep(0.2)

            child.sendline("quit")

            time.sleep(0.5)

            child.close(
                force=True
            )

        except Exception:
            pass


if __name__ == "__main__":
    main()