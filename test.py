import subprocess
import json
import re
import sys


def parse_line(line):
    line = line.rstrip()

    # NEW
    m = re.match(
        r"^\[NEW\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)$",
        line
    )
    if m:
        return {
            "event": "NEW",
            "address": m.group(1),
            "data": m.group(2)
        }

    # CHG
    m = re.match(
        r"^\[CHG\]\s+Device\s+([0-9A-Fa-f:]{17})\s+(.+)$",
        line
    )
    if m:
        address = m.group(1)
        change = m.group(2)

        if ":" in change:
            key, value = change.split(":", 1)
            key = key.strip()
            value = value.strip()

            if key.upper() == "RSSI":
                try:
                    value = int(value)
                except ValueError:
                    pass

            data = {
                key: value
            }
        else:
            data = {
                "raw": change
            }

        return {
            "event": "CHG",
            "address": address,
            "data": data
        }

    # DEL
    m = re.match(
        r"^\[DEL\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)$",
        line
    )
    if m:
        return {
            "event": "DEL",
            "address": m.group(1),
            "data": m.group(2)
        }

    return None


def main():

    print("Starting bluetoothctl...", flush=True)

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

    # Give bluetoothctl commands
    process.stdin.write("power on\n")
    process.stdin.flush()

    process.stdin.write("scan on\n")
    process.stdin.flush()

    print("Bluetooth scanning...", flush=True)

    try:

        while True:

            line = process.stdout.readline()

            if not line:
                break

            # ALWAYS print original bluetoothctl output
            print(line.rstrip(), flush=True)

            parsed = parse_line(line)

            if parsed:

                event = parsed["event"]

                output = {
                    "ble": {
                        event: parsed
                    }
                }

                # Print JSON
                print(
                    json.dumps(
                        output,
                        separators=(",", ":")
                    ),
                    flush=True
                )

    except KeyboardInterrupt:

        print("\nStopping...", flush=True)

    finally:

        try:
            process.stdin.write("scan off\n")
            process.stdin.flush()

            process.stdin.write("quit\n")
            process.stdin.flush()

        except Exception:
            pass

        process.terminate()
        process.wait()


if __name__ == "__main__":
    main()