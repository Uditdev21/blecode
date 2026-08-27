import json
import re
import threading
import time
import pexpect
import requests

# ============================================================
# CONFIGURATION
# ============================================================

API_URL = "http://localhost:8000/api/v1/data"
TOKEN = "tronn_sec_token_889900"
FLUSH_INTERVAL = 0.5  # Seconds between batch API dispatches (fast ingestion)
VERBOSE_PRINT = False  # Set to True to print every raw/parsed BLE line to terminal

running = True
batch = []
batch_lock = threading.Lock()

# Persistent HTTP session for fast connection reuse
session = requests.Session()
session.headers.update({
    "token": TOKEN,
    "Content-Type": "application/json",
})

# ============================================================
# PRE-COMPILED REGEX PATTERNS (HIGH PERFORMANCE)
# ============================================================

ANSI_REGEX = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
PROMPT_REGEX = re.compile(r"\[bluetoothctl\]>\s*")
NEW_REGEX = re.compile(r"^\[NEW\]\s+Device\s+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})(?:\s+(.*))?$")
DEL_REGEX = re.compile(r"^\[DEL\]\s+Device\s+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})(?:\s+(.*))?$")
CHG_REGEX = re.compile(r"^\[CHG\]\s+Device\s+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\s+(.+)$")
RSSI_REGEX = re.compile(r"RSSI:\s+0x[0-9A-Fa-f]+\s+\((-?\d+)\)")
MF_HEADER_REGEX = re.compile(r"^\[CHG\]\s+Device\s+([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\s+ManufacturerData\.Value:\s*$")
HEX_DATA_REGEX = re.compile(r"(?:[0-9A-Fa-f]{2}\s*)+")
MULTI_SPACE_REGEX = re.compile(r"\s+")


# ============================================================
# CLEAN ANSI / TERMINAL OUTPUT
# ============================================================

def clean_line(line: str) -> str:
    """
    Strips ANSI color codes, carriage returns, and bluetoothctl prompts.
    """
    line = ANSI_REGEX.sub("", line)
    line = line.replace("\r", "").replace("\x00", "").replace("\x08", "")
    line = PROMPT_REGEX.sub("", line)
    return line.strip()


# ============================================================
# PARSER
# ============================================================

def parse_line(line: str):
    """
    Parses a cleaned bluetoothctl terminal line into an event dict.
    """
    line = clean_line(line)
    if not line:
        return None

    # NEW Device
    match = NEW_REGEX.match(line)
    if match:
        return {
            "event": "NEW",
            "address": match.group(1),
            "data": match.group(2).strip() if match.group(2) else ""
        }

    # DEL Device
    match = DEL_REGEX.match(line)
    if match:
        return {
            "event": "DEL",
            "address": match.group(1),
            "data": match.group(2).strip() if match.group(2) else ""
        }

    # CHG Device
    match = CHG_REGEX.match(line)
    if match:
        address = match.group(1)
        change = match.group(2).strip()

        # RSSI
        rssi = RSSI_REGEX.search(change)
        if rssi:
            return {
                "event": "CHG",
                "address": address,
                "data": {
                    "RSSI": int(rssi.group(1))
                }
            }

        # Generic key:value
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

    return None


# ============================================================
# EVENT GROUPER
# ============================================================

def group_events(events):
    """
    Groups collected events into distinct collections for NEW, CHG, and DEL.
    """
    grouped = {
        "NEW": [],
        "CHG": [],
        "DEL": []
    }

    for ev in events:
        event_type = ev.get("event")
        entry = {k: v for k, v in ev.items() if k != "event"}
        if event_type in grouped:
            grouped[event_type].append(entry)
        else:
            grouped.setdefault(event_type, []).append(entry)

    return grouped


# ============================================================
# HIGH-SPEED API SENDER THREAD
# ============================================================

def api_sender():
    """
    Periodically flushes queued events to the REST API using persistent connection.
    """
    global running, batch

    while running:
        time.sleep(FLUSH_INTERVAL)

        with batch_lock:
            if not batch:
                continue
            events = batch
            batch = []

        payload = group_events(events)
        n_new = len(payload.get("NEW", []))
        n_chg = len(payload.get("CHG", []))
        n_del = len(payload.get("DEL", []))

        print(
            f"[API] Flushed {len(events)} events (NEW: {n_new}, CHG: {n_chg}, DEL: {n_del})",
            flush=True
        )

        try:
            response = session.post(
                API_URL,
                json=payload,
                timeout=5
            )
            if response.status_code != 201:
                print(f"[API WARN] HTTP {response.status_code}: {response.text}", flush=True)

        except Exception as e:
            print(f"[API ERROR] {type(e).__name__}: {e}", flush=True)


# ============================================================
# MAIN SCANNING LOOP
# ============================================================

def main():
    global running, batch

    print("Initializing bluetoothctl with high-speed duplicate scan...", flush=True)

    # Start bluetoothctl process
    child = pexpect.spawn("bluetoothctl", encoding="utf-8", timeout=1)
    child.logfile = None

    # Start background API dispatcher
    api_thread = threading.Thread(target=api_sender, daemon=True)
    api_thread.start()

    time.sleep(0.5)

    # Power ON Bluetooth
    child.sendline("power on")
    time.sleep(0.5)

    # Configure Scan Filters to allow DUPLICATE packets (disables packet suppression)
    print("Enabling duplicate-data scan filters in BlueZ...", flush=True)
    child.sendline("menu scan")
    time.sleep(0.2)
    child.sendline("clear")
    time.sleep(0.2)
    child.sendline("duplicate-data on")
    time.sleep(0.2)
    child.sendline("back")
    time.sleep(0.2)

    # Start Scanning
    child.sendline("scan on")
    print(">> High-speed Bluetooth scanning active (press Ctrl+C to stop)...", flush=True)

    buffer = ""
    pending_manufacturer = None

    try:
        while True:
            try:
                # Fast non-blocking read
                data = child.read_nonblocking(size=16384, timeout=0.02)
                if not data:
                    continue

                buffer += data

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.rstrip("\r")
                    if not line:
                        continue

                    if VERBOSE_PRINT:
                        print(line, flush=True)

                    cleaned = clean_line(line)
                    if not cleaned:
                        continue

                    # Check for multi-line ManufacturerData.Value header
                    match = MF_HEADER_REGEX.match(cleaned)
                    if match:
                        pending_manufacturer = {
                            "event": "CHG",
                            "address": match.group(1),
                            "data": {"ManufacturerData.Value": None}
                        }
                        continue

                    # Handle ManufacturerData.Value payload line
                    if pending_manufacturer:
                        hex_data = MULTI_SPACE_REGEX.sub(" ", cleaned.strip())
                        if HEX_DATA_REGEX.fullmatch(hex_data):
                            pending_manufacturer["data"]["ManufacturerData.Value"] = hex_data
                            with batch_lock:
                                batch.append(pending_manufacturer)
                            pending_manufacturer = None
                            continue
                        pending_manufacturer = None

                    # Normal Line Parsing
                    parsed = parse_line(cleaned)
                    if parsed:
                        if VERBOSE_PRINT:
                            print("[PARSED]", json.dumps(parsed), flush=True)
                        with batch_lock:
                            batch.append(parsed)

            except pexpect.TIMEOUT:
                continue

            except pexpect.EOF:
                print("[BLE] bluetoothctl process ended", flush=True)
                break

    except KeyboardInterrupt:
        print("\nStopping scan gracefully...", flush=True)

    finally:
        running = False

        # Flush final remaining events
        with batch_lock:
            remaining = batch.copy()
            batch.clear()

        if remaining:
            final_payload = group_events(remaining)
            print(f"[API] Sending final {len(remaining)} events...", flush=True)
            try:
                session.post(API_URL, json=final_payload, timeout=5)
            except Exception as e:
                print(f"[API ERROR] Final flush error: {e}", flush=True)

        # Stop bluetoothctl
        try:
            child.sendline("scan off")
            time.sleep(0.2)
            child.sendline("quit")
            time.sleep(0.2)
            child.close(force=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()