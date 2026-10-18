import json
import tempfile
from pathlib import Path

from .engine import Operations


def main():
    with tempfile.TemporaryDirectory() as folder:
        ops = Operations(Path(folder) / "operations.db", lambda: 1800000000)
        commands = [
            ("vessel.create", {"vessel": "training-vessel"}),
            ("crew.register", {"vessel": "training-vessel", "crew": "operator-1", "name": "Training Operator"}),
            ("certificate.set", {"crew": "operator-1", "certificate": "BST", "expires": 1800001000}),
            ("station.configure", {"vessel": "training-vessel", "station": "muster-a", "minimum": 1, "capacity": 4, "certificate": "BST"}),
            ("drill.start", {"vessel": "training-vessel", "drill": "exercise-1"}),
            ("drill.check_in", {"drill": "exercise-1", "crew": "operator-1", "station": "muster-a"}),
            ("drill.close", {"drill": "exercise-1"}),
        ]
        output = []
        for index, (command, payload) in enumerate(commands):
            output.append({"command": command, "result": ops.execute("training-operator", str(index), command, payload)})
        backup = Path(folder) / "restored.db"
        ops.backup(backup)
        restored = Operations(backup)
        print(json.dumps({"input": "synthetic training fixture", "execution": "real SQLite transactions and backup restore", "commands": output, "restored_report": restored.report("exercise-1"), "audit_valid": restored.verify(), "events": len(restored.audit())}, indent=2))


if __name__ == "__main__":
    main()
