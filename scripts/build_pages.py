import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offshore.engine import Operations
from offshore.planner import plan


def build(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for asset in (Path(__file__).resolve().parents[1] / 'web').iterdir():
        if asset.is_file():
            shutil.copy2(asset, destination / asset.name)
    with tempfile.TemporaryDirectory() as folder:
        now = int(datetime(2026, 10, 18, 12, tzinfo=timezone.utc).timestamp())
        ops = Operations(Path(folder) / 'training.db', lambda: now)
        sequence = 0

        def execute(command, **payload):
            nonlocal sequence
            sequence += 1
            return ops.execute('training-operator', str(sequence), command, payload)

        execute('vessel.create', vessel='OC-ATLANTIC')
        people = [('crew-01', 'Alex Morgan', 'Bridge officer'), ('crew-02', 'Sam Costa', 'Marine technician'), ('crew-03', 'Jordan Silva', 'Electrical technician'), ('crew-04', 'Taylor Santos', 'Deck operator'), ('crew-05', 'Casey Lima', 'Medic'), ('crew-06', 'Robin Alves', 'Mechanical technician')]
        for person, name, role in people:
            execute('crew.register', vessel='OC-ATLANTIC', crew=person, name=name)
            execute('certificate.set', crew=person, certificate='BST', expires=now + 86400 * 180)
        execute('station.configure', vessel='OC-ATLANTIC', station='Alpha', minimum=2, capacity=3, certificate='BST')
        execute('station.configure', vessel='OC-ATLANTIC', station='Bravo', minimum=2, capacity=3, certificate='BST')
        execute('drill.start', vessel='OC-ATLANTIC', drill='DRILL-001')
        execute('drill.check_in', drill='DRILL-001', crew='crew-01', station='Alpha')
        execute('drill.check_in', drill='DRILL-001', crew='crew-02', station='Bravo')
        snapshot = {'generated_at': datetime.now(timezone.utc).isoformat(), 'scenario_at': datetime.fromtimestamp(now, timezone.utc).isoformat(), 'source': 'Synthetic training data executed through the Python/SQLite engine', 'report': ops.report('DRILL-001'), 'plan': plan(ops, 'DRILL-001'), 'crew': [{'id': person, 'name': name, 'role': role} for person, name, role in people], 'audit': ops.audit(), 'audit_valid': ops.verify()}
        (destination / 'snapshot.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    (destination / '.nojekyll').touch()


if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else 'dist')
