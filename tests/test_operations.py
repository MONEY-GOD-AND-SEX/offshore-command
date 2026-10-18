import concurrent.futures
import sqlite3
import tempfile
import unittest
from pathlib import Path

from offshore import Conflict, Operations


class OperationsFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ops.db"
        self.now = 1800000000
        self.ops = Operations(self.path, lambda: self.now)
        self.sequence = 0
        self.run_command("vessel.create", vessel="v1")
        for crew in ("alice", "bob"):
            self.run_command("crew.register", vessel="v1", crew=crew, name=crew.title())
            self.run_command("certificate.set", crew=crew, certificate="BST", expires=self.now + 100)
        self.run_command("station.configure", vessel="v1", station="muster", minimum=1, capacity=2, certificate="BST")

    def run_command(self, command, **data):
        self.sequence += 1
        return self.ops.execute("operator", str(self.sequence), command, data)

    def start(self):
        self.run_command("drill.start", vessel="v1", drill="d1")

    def check_in(self, crew="alice", station="muster"):
        return self.run_command("drill.check_in", drill="d1", crew=crew, station=station)


class OperationsTests(OperationsFixture):
    def test_full_lifecycle_survives_restart_and_backup(self):
        self.start()
        self.check_in()
        self.assertEqual(self.ops.report("d1")["missing"], ["bob"])
        self.check_in("bob")
        self.now += 5
        closed = self.run_command("drill.close", drill="d1")
        self.assertEqual(closed["elapsed_seconds"], 5)
        copy = Path(self.temp.name) / "backup.db"
        self.ops.backup(copy)
        restored = Operations(copy, lambda: self.now)
        self.assertEqual(restored.report("d1")["state"], "closed")
        self.assertTrue(restored.verify())
        self.assertEqual(restored.audit(), self.ops.audit())

    def test_retry_is_exact_and_conflicting_reuse_rolls_back(self):
        data = {"vessel": "v2"}
        first = self.ops.execute("operator", "retry", "vessel.create", data)
        events = len(self.ops.audit())
        self.assertEqual(first, self.ops.execute("operator", "retry", "vessel.create", data))
        with self.assertRaises(Conflict):
            self.ops.execute("operator", "retry", "vessel.create", {"vessel": "v3"})
        self.assertEqual(len(self.ops.audit()), events)

    def test_isolation_missing_qualification_and_station_conflict(self):
        self.run_command("vessel.create", vessel="v2")
        self.run_command("crew.register", vessel="v2", crew="outsider", name="Other")
        self.run_command("station.configure", vessel="v1", station="bridge", minimum=0, capacity=2, certificate="BST")
        self.start()
        with self.assertRaises(Conflict):
            self.check_in("outsider")
        self.check_in()
        with self.assertRaises(Conflict):
            self.check_in(station="bridge")
        self.now += 101
        with self.assertRaises(Conflict):
            self.check_in("bob")
        with self.assertRaises(Conflict):
            self.run_command("drill.close", drill="d1")

    def test_manifest_and_station_requirements_are_snapshotted(self):
        self.start()
        self.run_command("crew.register", vessel="v1", crew="late", name="Late")
        self.run_command("station.configure", vessel="v1", station="muster", minimum=0, capacity=10, certificate="NEW")
        self.check_in()
        report = self.ops.report("d1")
        self.assertEqual(report["missing"], ["bob"])
        self.assertEqual(report["stations"][0]["capacity"], 2)
        self.assertEqual(report["stations"][0]["eligible"], 1)

    def test_duplicate_attendance_does_not_duplicate_people(self):
        self.start()
        self.check_in()
        self.assertTrue(self.check_in()["duplicate"])
        self.assertEqual(self.ops.report("d1")["stations"][0]["present"], 1)

    def test_one_active_drill_per_vessel(self):
        self.start()
        with self.assertRaises(Conflict):
            self.run_command("drill.start", vessel="v1", drill="d2")

    def test_concurrent_writers_cannot_overbook(self):
        self.run_command("station.configure", vessel="v1", station="muster", minimum=1, capacity=1, certificate="BST")
        self.start()

        def check(crew):
            try:
                self.ops.execute("operator", "parallel-" + crew, "drill.check_in", {"drill": "d1", "crew": crew, "station": "muster"})
                return True
            except Conflict:
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(check, ["alice", "bob"]))
        self.assertEqual(sum(results), 1)
        self.assertTrue(self.ops.verify())

    def test_expiry_after_arrival_blocks_closure(self):
        self.start()
        self.check_in()
        self.check_in("bob")
        self.now += 100
        self.assertFalse(self.ops.report("d1")["ready"])
        with self.assertRaises(Conflict):
            self.run_command("drill.close", drill="d1")

    def test_failed_command_has_no_partial_audit_or_request(self):
        before = self.ops.audit()
        with self.assertRaises(Conflict):
            self.run_command("crew.register", vessel="unknown", crew="bad", name="Bad")
        self.assertEqual(self.ops.audit(), before)

    def test_audit_rejects_mutation_and_detects_altered_content(self):
        with sqlite3.connect(self.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM events")
            db.execute("DROP TRIGGER events_no_update")
            db.execute("UPDATE events SET actor='tampered' WHERE seq=1")
        self.assertFalse(self.ops.verify())

    def test_invalid_parameters(self):
        with self.assertRaises(ValueError):
            self.run_command("station.configure", vessel="v1", station="x", minimum=2, capacity=1, certificate="BST")
        with self.assertRaises(ValueError):
            self.run_command("certificate.set", crew="alice", certificate="BST", expires=self.now)


if __name__ == "__main__":
    unittest.main()
