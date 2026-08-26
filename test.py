import subprocess
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


def parse_line(line):
    line = line.strip()

    # Ignore bluetoothctl prompt
    if line == "[bluetoothctl]>":
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
        rssi_match = re.match(
            r"^RSSI:\s+0x[0-9a-fA-F]+\s+\((-?\d+)\)$",
            change
        )

        if rssi_match:

            return {
                "event": "CHG",
                "address": address,
                "data": {
                    "RSSI": int(rssi_match.group(1))
                }
            }

        # Other CHG data
        if ":" in change:

            key, value = change.split(":", 1)

            key = key.strip()
            value = value.strip()

            # Try to convert hexadecimal values
            hex_match = re.match(
                r"^0x([0-9a-fA-F]+)",
                value
            )

            if hex_match:

                try:
                    value = int(
                        hex_match.group(1),
                        16
                    )
                except ValueError:
                    pass

            return {
                "event": "CHG",
                "address": address,
                "data": {
                    key: value
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


def send_batch_loop():

    global running

    while running:

        # Wait one second
        time.sleep(1)

        # Get current events
        with batch_lock:

            if not batch:
                continue

            current_batch = batch.copy()
            batch.clear()

        payload = {
            "ble": current_batch
        }

        print(
            f"[API] Sending {len(current_batch)} events...",
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
                f"[API] Status: {response.status_code}",
                flush=True
            )

            print(
                f"[API] Response: {response.text}",
                flush=True
            )

        except Exception as e:

            print(
                f"[API ERROR] {repr(e)}",
                flush=True
            )


def bluetooth_reader(process):

    global running

    while running:

        line = process.stdout.readline()

        if not line:
            print(
                "[BLE] bluetoothctl closed.",
                flush=True
            )
            running = False
            break

        # Print original output
        print(
            line.rstrip(),
            flush=True
        )

        parsed = parse_line(line)

        if parsed:

            # Print parsed event
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

            # Add to API batch
            with batch_lock:
                batch.append(parsed)


def main():

    global running

    print(
        "Starting bluetoothctl...",
        flush=True
    )

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
    # Start API thread FIRST
    # ---------------------------------------------------------

    api_thread = threading.Thread(
        target=send_batch_loop,
        daemon=True
    )

    api_thread.start()

    # ---------------------------------------------------------
    # Start Bluetooth reader
    # ---------------------------------------------------------

    ble_thread = threading.Thread(
        target=bluetooth_reader,
        args=(process,),
        daemon=True
    )

    ble_thread.start()

    # ---------------------------------------------------------
    # Bluetooth commands
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

        while running:

            time.sleep(1)

    except KeyboardInterrupt:

        print(
            "\nStopping...",
            flush=True
        )

    finally:

        running = False

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

        # Send remaining events
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
                    f"[API] Final status: {response.status_code}",
                    flush=True
                )

            except Exception as e:

                print(
                    f"[API ERROR] {repr(e)}",
                    flush=True
                )


if __name__ == "__main__":
    main()