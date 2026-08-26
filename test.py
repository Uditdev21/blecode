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
# CLEAN ANSI / TERMINAL OUTPUT
# ============================================================

def clean_line(line):
    """
    Convert bluetoothctl terminal output into clean text.

    Example:

    \x1b[0;94m[bluetoothctl]> \x1b[0m\r\x1b[K\r
    [\x1b[0;93mCHG\x1b[0m] Device ...

    becomes:

    [CHG] Device ...
    """

    # Remove ANSI escape sequences
    line = re.sub(
        r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])",
        "",
        line
    )

    # Remove carriage return
    line = line.replace("\r", "")

    # Remove terminal control characters
    line = line.replace("\x00", "")
    line = line.replace("\x08", "")

    # Remove bluetoothctl prompt
    line = re.sub(
        r"\[bluetoothctl\]>\s*",
        "",
        line
    )

    return line.strip()


# ============================================================
# PARSER
# ============================================================

def parse_line(line):

    line = clean_line(line)

    if not line:
        return None

    # --------------------------------------------------------
    # NEW
    # --------------------------------------------------------

    match = re.match(
        r"^\[NEW\]\s+Device\s+"
        r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})"
        r"(?:\s+(.*))?$",
        line
    )

    if match:

        return {
            "event": "NEW",
            "address": match.group(1),
            "data": (
                match.group(2).strip()
                if match.group(2)
                else ""
            )
        }

    # --------------------------------------------------------
    # DEL
    # --------------------------------------------------------

    match = re.match(
        r"^\[DEL\]\s+Device\s+"
        r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})"
        r"(?:\s+(.*))?$",
        line
    )

    if match:

        return {
            "event": "DEL",
            "address": match.group(1),
            "data": (
                match.group(2).strip()
                if match.group(2)
                else ""
            )
        }

    # --------------------------------------------------------
    # CHG
    # --------------------------------------------------------

    match = re.match(
        r"^\[CHG\]\s+Device\s+"
        r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})"
        r"\s+(.+)$",
        line
    )

    if match:

        address = match.group(1)
        change = match.group(2).strip()

        # ----------------------------------------------------
        # RSSI
        # ----------------------------------------------------

        rssi = re.search(
            r"RSSI:\s+0x[0-9A-Fa-f]+\s+\((-?\d+)\)",
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

        # ----------------------------------------------------
        # Generic key:value
        # ----------------------------------------------------

        if ":" in change:

            key, value = change.split(":", 1)

            return {
                "event": "CHG",
                "address": address,
                "data": {
                    key.strip(): value.strip()
                }
            }

        # ----------------------------------------------------
        # Unknown CHG
        # ----------------------------------------------------

        return {
            "event": "CHG",
            "address": address,
            "data": {
                "raw": change
            }
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

        # Get current batch
        with batch_lock:

            events = batch
            batch = []

        # Nothing to send
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
                f"[API ERROR] "
                f"{type(e).__name__}: {e}",
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

    # --------------------------------------------------------
    # Start bluetoothctl using a REAL PTY
    # --------------------------------------------------------

    child = pexpect.spawn(
        "bluetoothctl",
        encoding="utf-8",
        timeout=1
    )

    # Do not automatically print pexpect output
    child.logfile = None

    # --------------------------------------------------------
    # Start API sender
    # --------------------------------------------------------

    api_thread = threading.Thread(
        target=api_sender,
        daemon=True
    )

    api_thread.start()

    # --------------------------------------------------------
    # Give bluetoothctl time to start
    # --------------------------------------------------------

    time.sleep(1)

    # --------------------------------------------------------
    # Power Bluetooth ON
    # --------------------------------------------------------

    child.sendline("power on")

    time.sleep(1)

    # --------------------------------------------------------
    # Start scan
    # --------------------------------------------------------

    child.sendline("scan on")

    print(
        "Bluetooth scanning...",
        flush=True
    )

    # --------------------------------------------------------
    # Read output
    # --------------------------------------------------------

    buffer = ""

    # Used for ManufacturerData.Value
    pending_manufacturer = None

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

                # ------------------------------------------------
                # Process complete lines
                # ------------------------------------------------

                while "\n" in buffer:

                    line, buffer = buffer.split(
                        "\n",
                        1
                    )

                    line = line.rstrip("\r")

                    if not line:
                        continue

                    # ------------------------------------------------
                    # Print raw terminal line
                    # ------------------------------------------------

                    print(
                        line,
                        flush=True
                    )

                    # ------------------------------------------------
                    # Clean line
                    # ------------------------------------------------

                    cleaned = clean_line(line)

                    if not cleaned:
                        continue

                    # =================================================
                    # ManufacturerData.Value HEADER
                    # =================================================

                    match = re.match(
                        r"^\[CHG\]\s+Device\s+"
                        r"([0-9A-Fa-f]{2}"
                        r"(?::[0-9A-Fa-f]{2}){5})"
                        r"\s+ManufacturerData\.Value:\s*$",
                        cleaned
                    )

                    if match:

                        pending_manufacturer = {
                            "event": "CHG",
                            "address": match.group(1),
                            "data": {
                                "ManufacturerData.Value": None
                            }
                        }

                        continue

                    # =================================================
                    # ManufacturerData.Value DATA
                    # =================================================

                    if pending_manufacturer:

                        hex_data = cleaned.strip()

                        # Remove spaces used for terminal formatting
                        hex_data = re.sub(
                            r"\s+",
                            " ",
                            hex_data
                        )

                        # Check whether it is hexadecimal bytes
                        if re.fullmatch(
                            r"(?:[0-9A-Fa-f]{2}\s*)+",
                            hex_data
                        ):

                            pending_manufacturer[
                                "data"
                            ][
                                "ManufacturerData.Value"
                            ] = hex_data

                            print(
                                "[PARSED]",
                                json.dumps(
                                    pending_manufacturer,
                                    separators=(",", ":")
                                ),
                                flush=True
                            )

                            with batch_lock:

                                batch.append(
                                    pending_manufacturer
                                )

                            pending_manufacturer = None

                            continue

                        # Something else appeared,
                        # so don't keep stale state
                        pending_manufacturer = None

                    # =================================================
                    # NORMAL PARSER
                    # =================================================

                    parsed = parse_line(cleaned)

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

            # --------------------------------------------------------
            # No data available right now
            # --------------------------------------------------------

            except pexpect.TIMEOUT:

                continue

            # --------------------------------------------------------
            # bluetoothctl exited
            # --------------------------------------------------------

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

        # ============================================================
        # SEND REMAINING EVENTS
        # ============================================================

        with batch_lock:

            remaining = batch.copy()

            batch.clear()

        if remaining:

            print(
                f"[API] Sending final "
                f"{len(remaining)} events...",
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
                    f"[API] Final HTTP "
                    f"{response.status_code}",
                    flush=True
                )

                print(
                    f"[API] Final Response: "
                    f"{response.text}",
                    flush=True
                )

            except Exception as e:

                print(
                    f"[API ERROR] "
                    f"{type(e).__name__}: {e}",
                    flush=True
                )

        # ============================================================
        # STOP BLUETOOTHCTL
        # ============================================================

        try:

            child.sendline("scan off")

            time.sleep(0.2)

            child.sendline("quit")

            time.sleep(0.5)

            child.close(force=True)

        except Exception:

            pass


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()