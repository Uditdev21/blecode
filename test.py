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