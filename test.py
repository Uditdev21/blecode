import pexpect
import json
import re
import time
import threading
import requests


API_URL = "http://localhost:8000/api/v1/data"
TOKEN = "tronn_sec_token_889900"

running = True

batch = []
batch_lock = threading.Lock()


# ============================================================
# PARSER
# ============================================================
def parse_line(line):
    line = line.strip()

    # Remove bluetoothctl prompt
    line = re.sub(r"^\[bluetoothctl\]>\s*", "", line)

    if not line:
        return None

    # --------------------------------------------------------
    # NEW
    # --------------------------------------------------------
    m = re.search(
        r"\[NEW\]\s+Device\s+([0-9A-Fa-f:\\]{17,23})\s*(.*)",
        line
    )

    if m:
        address = m.group(1).replace("\\", "")
        name = m.group(2).strip()

        return {
            "event": "NEW",
            "address": address,
            "data": name
        }

    # --------------------------------------------------------
    # CHG
    # --------------------------------------------------------
    m = re.search(
        r"\[CHG\]\s+Device\s+([0-9A-Fa-f:\\]{17,23})\s+(.+)",
        line
    )

    if m:
        address = m.group(1).replace("\\", "")
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

    # --------------------------------------------------------
    # DEL
    # --------------------------------------------------------
    m = re.search(
        r"\[DEL\]\s+Device\s+([0-9A-Fa-f:\\]{17,23})\s*(.*)",
        line
    )

    if m:
        address = m.group(1).replace("\\", "")
        name = m.group(2).strip()

        return {
            "event": "DEL",
            "address": address,
            "data": name
        }

    return None


# ============================================================
# API SENDER
# ============================================================

def api_sender():

    global running
    global batch

    while running:

        time.sleep(1)

        # Get events collected during this second
        with batch_lock:

            events = batch
            batch = []

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

    print(
        "Starting bluetoothctl...",
        flush=True
    )

    # --------------------------------------------------------
    # Start bluetoothctl with a REAL PTY
    # --------------------------------------------------------

    child = pexpect.spawn(
        "bluetoothctl",
        encoding="utf-8",
        timeout=1
    )

    # Print bluetoothctl output
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
    # Wait for bluetoothctl
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

                # Read whatever bluetoothctl gives us
                data = child.read_nonblocking(
                    size=4096,
                    timeout=0.2
                )

                if not data:
                    continue

                buffer += data

                # Split into lines
                while "\n" in buffer:

                    line, buffer = buffer.split(
                        "\n",
                        1
                    )

                    line = line.strip()

                    if not line:
                        continue

                    # Print original bluetoothctl output
                    print(
                        line,
                        flush=True
                    )

                    # Parse
                    parsed = parse_line(line)

                    if parsed:

                        # Print parsed event
                        print(
                            "[PARSED]",
                            json.dumps(
                                parsed,
                                separators=(",", ":")
                            ),
                            flush=True
                        )

                        # Add to batch
                        with batch_lock:
                            batch.append(parsed)

            except pexpect.TIMEOUT:

                # Normal — just means no output
                # during this 200ms period.
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

        # ----------------------------------------------------
        # Send remaining events
        # ----------------------------------------------------

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

            except Exception as e:

                print(
                    f"[API ERROR] {e}",
                    flush=True
                )

        # ----------------------------------------------------
        # Stop bluetoothctl
        # ----------------------------------------------------

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