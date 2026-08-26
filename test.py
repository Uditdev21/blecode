import subprocess
import json
import re
import time
import threading
import requests


API_URL = "http://localhost:8000/api/v1/data"
TOKEN = "tronn_sec_token_889900"

batch = []
batch_lock = threading.Lock()
running = True


def parse_line(line):
    line = line.strip()

    # Remove bluetoothctl prompt
    line = re.sub(r"^\[bluetoothctl\]>\s*", "", line)

    if not line:
        return None

    # NEW
    m = re.search(
        r"\[NEW\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)",
        line
    )

    if m:
        return {
            "event": "NEW",
            "address": m.group(1),
            "data": m.group(2).strip()
        }

    # CHG
    m = re.search(
        r"\[CHG\]\s+Device\s+([0-9A-Fa-f:]{17})\s+(.+)",
        line
    )

    if m:

        address = m.group(1)
        change = m.group(2).strip()

        # RSSI
        rssi = re.search(
            r"RSSI:\s+0x[0-9a-fA-F]+\s+\((-?\d+)\)",
            change
        )

        if rssi:

            return {
                "event": "CHG",
                "address": address,
                "data": {
                    "RSSI": int(rssi.group(1))
                }
            }

        # Generic CHG
        if ":" in change:

            key, value = change.split(":", 1)

            return {
                "event": "CHG",
                "address": address,
                "data": {
                    key.strip(): value.strip()
                }
            }

        return {
            "event": "CHG",
            "address": address,
            "data": {
                "raw": change
            }
        }

    # DEL
    m = re.search(
        r"\[DEL\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)",
        line
    )

    if m:

        return {
            "event": "DEL",
            "address": m.group(1),
            "data": m.group(2).strip()
        }

    return None


def api_sender():

    global running

    while running:

        time.sleep(1)

        with batch_lock:

            events = batch.copy()
            batch.clear()

        if not events:
            print(
                "[API] 0 events",
                flush=True
            )
            continue

        payload = {
            "ble": events
        }

        print(
            f"[API] Sending {len(events)} events",
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
                f"[API ERROR] {e}",
                flush=True
            )


def main():

    global running

    print(
        "Starting bluetooth scan...",
        flush=True
    )

    # ---------------------------------------------------------
    # Start bluetoothctl in interactive mode
    # ---------------------------------------------------------

    process = subprocess.Popen(
        [
            "bluetoothctl"
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # ---------------------------------------------------------
    # API thread
    # ---------------------------------------------------------

    threading.Thread(
        target=api_sender,
        daemon=True
    ).start()

    # ---------------------------------------------------------
    # Commands
    # ---------------------------------------------------------

    time.sleep(1)

    process.stdin.write("power on\n")
    process.stdin.flush()

    time.sleep(1)

    process.stdin.write("scan on\n")
    process.stdin.flush()

    print(
        "Bluetooth scanning...",
        flush=True
    )

    try:

        while True:

            line = process.stdout.readline()

            if not line:
                break

            # Print original
            print(
                line.rstrip(),
                flush=True
            )

            parsed = parse_line(line)

            if parsed:

                print(
                    "[PARSED]",
                    json.dumps(
                        parsed,
                        separators=(",", ":")
                    ),
                    flush=True
                )

                with batch_lock:
                    batch.append(parsed)

    except KeyboardInterrupt:

        print(
            "\nStopping...",
            flush=True
        )

    finally:

        running = False

        # Send remaining events
        with batch_lock:

            remaining = batch.copy()
            batch.clear()

        if remaining:

            print(
                f"[API] Sending final {len(remaining)} events",
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
                    f"[API] HTTP {response.status_code}",
                    flush=True
                )

            except Exception as e:

                print(
                    f"[API ERROR] {e}",
                    flush=True
                )

        try:

            process.stdin.write("scan off\n")
            process.stdin.flush()

            process.stdin.write("quit\n")
            process.stdin.flush()

        except Exception:
            pass

        try:

            process.terminate()
            process.wait(timeout=2)

        except Exception:

            try:
                process.kill()
            except Exception:
                pass


if __name__ == "__main__":
    main()