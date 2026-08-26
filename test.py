import subprocess
import json
import re


def parse_bluetoothctl_line(line):
    line = line.rstrip()

    # [NEW] Device XX:XX:XX:XX:XX:XX Name
    new_match = re.match(
        r"^\[NEW\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)$",
        line
    )

    # [CHG] Device XX:XX:XX:XX:XX:XX RSSI: -45
    chg_match = re.match(
        r"^\[CHG\]\s+Device\s+([0-9A-Fa-f:]{17})\s+(.+)$",
        line
    )

    # [DEL] Device XX:XX:XX:XX:XX:XX Name
    del_match = re.match(
        r"^\[DEL\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)$",
        line
    )

    if new_match:
        return {
            "type": "NEW",
            "address": new_match.group(1),
            "data": new_match.group(2)
        }

    if chg_match:
        address = chg_match.group(1)
        change = chg_match.group(2)

        # Split CHG property/value
        if ":" in change:
            key, value = change.split(":", 1)
            key = key.strip()
            value = value.strip()

            # Convert RSSI to integer
            if key.lower() == "rssi":
                try:
                    value = int(value)
                except ValueError:
                    pass

            change_data = {
                key: value
            }
        else:
            change_data = {
                "raw": change
            }

        return {
            "type": "CHG",
            "address": address,
            "data": change_data
        }

    if del_match:
        return {
            "type": "DEL",
            "address": del_match.group(1),
            "data": del_match.group(2)
        }

    return None


def main():
    process = subprocess.Popen(
        ["bluetoothctl"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    process.stdin.write("scan on\n")
    process.stdin.flush()

    print("Bluetooth scanning...\n")

    try:
        for line in process.stdout:
            parsed = parse_bluetoothctl_line(line)

            if parsed:
                output = {
                    "ble": {
                        parsed["type"]: parsed
                    }
                }

                print(json.dumps(output, separators=(",", ":")))

    except KeyboardInterrupt:
        pass

    finally:
        try:
            process.stdin.write("scan off\n")
            process.stdin.write("quit\n")
            process.stdin.flush()
        except:
            pass

        process.terminate()


if __name__ == "__main__":
    main()