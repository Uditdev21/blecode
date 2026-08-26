import subprocess
import json
import re
import time
import requests


API_URL = "http://localhost:8000/api/v1/data"
TOKEN = "tronn_sec_token_889900"

running = True
batch = []


def parse_line(line):
    line = line.rstrip()

    # Ignore bluetoothctl prompt
    line = line.replace("[bluetoothctl]> ", "").strip()

    if not line:
        return None

    # ---------------------------------------------------------
    # NEW
    # ---------------------------------------------------------
    m = re.match(
        r"^\[NEW\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)$",
        line
    )

    if m:
        return {
            "event": "NEW",
            "address": m.group(1),
            "data": m.group(2).strip()
        }

    # ---------------------------------------------------------
    # CHG
    # ---------------------------------------------------------
    m = re.match(
        r"^\[CHG\]\s+Device\s+([0-9A-Fa-f:]{17})\s+(.+)$",
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

    # ---------------------------------------------------------
    # DEL
    # ---------------------------------------------------------
    m = re.match(
        r"^\[DEL\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)$",
        line
    )

    if m:
        return {
            "event": "DEL",
            "address": m.group(1),
            "data": m.group(2).strip()
        }

    return None


def send_to_api(events):

    if not events:
        return

    payload = {
        "ble": events
    }

    print(
        f"\n[API] Sending {len(events)} events",
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


def main():

    global running
    global batch

    print(
        "Starting bluetoothctl...",
        flush=True
    )

    process = subprocess.Popen(
        [
            "stdbuf",
            "-oL",
            "-eL",
            "bluetoothctl"
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # ---------------------------------------------------------
    # Start bluetoothctl
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

    # API timer
    next_api_send = time.monotonic() + 1

    try:

        while running:

            # -------------------------------------------------
            # Read bluetoothctl output
            # -------------------------------------------------

            line = process.stdout.readline()

            if not line:

                print(
                    "[BLE] bluetoothctl stopped",
                    flush=True
                )

                break

            # Always print raw output
            print(
                line.rstrip(),
                flush=True
            )

            # -------------------------------------------------
            # Parse event
            # -------------------------------------------------

            parsed = parse_line(line)

            if parsed:

                # Print JSON event
                print(
                    json.dumps(
                        {
                            "ble": {
                                parsed["event"]: parsed
                            }
                        },
                        separators=(",", ":")
                    ),
                    flush=True
                )

                # Add to batch
                batch.append(parsed)

            # -------------------------------------------------
            # Every 1 second send API
            # -------------------------------------------------

            now = time.monotonic()

            if now >= next_api_send:

                if batch:

                    events_to_send = batch
                    batch = []

                    send_to_api(
                        events_to_send
                    )

                else:

                    print(
                        "[API] 0 events",
                        flush=True
                    )

                next_api_send = now + 1

    except KeyboardInterrupt:

        print(
            "\nStopping...",
            flush=True
        )

    finally:

        running = False

        # -----------------------------------------------------
        # Send remaining events
        # -----------------------------------------------------

        if batch:

            print(
                f"[API] Sending final {len(batch)} events",
                flush=True
            )

            send_to_api(batch)

            batch = []

        # -----------------------------------------------------
        # Stop bluetoothctl
        # -----------------------------------------------------

        try:

            process.stdin.write("scan off\n")
            process.stdin.flush()

            time.sleep(0.2)

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