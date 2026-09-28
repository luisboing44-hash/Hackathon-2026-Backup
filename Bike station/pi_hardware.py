"""Template that connects the Pi's card reader and sensors to SmartRack.
Uses only Python's standard library. Fill in the TODO parts for your hardware.
Run the app first (bash start.sh), then run this in a second terminal."""
import json, urllib.request

URL = "http://localhost:5000"


def _post(path, data):
    req = urllib.request.Request(URL + path, json.dumps(data).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.load(r)


def send_scan(card_uid, slot):
    """A card was scanned at bike park slot `slot`. Parks, unlocks or denies automatically."""
    return _post("/api/scan", {"card": card_uid, "rail": slot})


def send_alarm(slot, reason="vibration"):
    """A sensor detected the bike moving without a scan."""
    return _post("/api/alarm", {"rail": slot, "reason": reason})


if __name__ == "__main__":
    # Quick test without any hardware:
    print(send_scan("A1B2C3D4", 1))
    # TODO: replace the test above with your real loop, for example:
    #   while True:
    #       uid = read_card()            # your RFID reader code
    #       if uid: send_scan(uid, 1)
    #       if vibration_detected(): send_alarm(1, "vibration")
