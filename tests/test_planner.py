import itertools

from offshore.planner import plan
from test_operations import OperationsFixture


class PlannerTests(OperationsFixture):
    def test_reroutes_flexible_crew_to_preserve_scarce_qualification(self):
        self.run_command("certificate.set", crew="alice", certificate="MED", expires=self.now + 100)
        self.run_command("station.configure", vessel="v1", station="medical", minimum=1, capacity=1, certificate="MED")
        self.start()
        result = plan(self.ops, "d1")
        self.assertTrue(result["feasible"])
        self.assertEqual(result["assignments"], {"alice": "medical", "bob": "muster"})
        self.assertEqual(self.ops.report("d1")["missing"], ["alice", "bob"])

    def test_reports_impossible_qualification_without_claiming_readiness(self):
        self.run_command("station.configure", vessel="v1", station="medical", minimum=1, capacity=1, certificate="MED")
        self.start()
        result = plan(self.ops, "d1")
        self.assertFalse(result["feasible"])
        self.assertEqual(result["deficits"]["medical"], 1)

    def test_keeps_actual_attendance_fixed(self):
        self.start()
        self.check_in()
        result = plan(self.ops, "d1")
        self.assertEqual(result["fixed"], {"alice": "muster"})
        self.assertTrue(result["feasible"])

    def test_expired_fixed_member_is_not_eligible(self):
        self.start()
        self.check_in()
        self.now += 100
        result = plan(self.ops, "d1")
        self.assertFalse(result["feasible"])
        self.assertEqual(result["invalid_fixed"], ["alice"])

    def test_closed_report_does_not_change_with_certificate_renewal(self):
        self.start()
        self.check_in()
        self.check_in("bob")
        self.run_command("drill.close", drill="d1")
        before = self.ops.report("d1")
        self.now += 200
        self.run_command("certificate.set", crew="alice", certificate="BST", expires=self.now + 500)
        self.assertEqual(before, self.ops.report("d1"))

    def test_solver_matches_exhaustive_feasibility_for_small_graphs(self):
        with self.ops.connection() as db:
            db.execute("DELETE FROM stations")
        for name in ("a", "b"):
            self.run_command("station.configure", vessel="v1", station=name, minimum=1, capacity=1, certificate=name)
        self.start()
        for mask in range(16):
            with self.ops.connection() as db:
                db.execute("DELETE FROM certificates")
                eligible = set()
                for bit, pair in enumerate(itertools.product(("alice", "bob"), ("a", "b"))):
                    if mask & (1 << bit):
                        db.execute("INSERT INTO certificates VALUES(?,?,?)", (*pair, self.now + 100))
                        eligible.add(pair)
            expected = any(("alice", a) in eligible and ("bob", b) in eligible for a, b in (("a", "b"), ("b", "a")))
            self.assertEqual(plan(self.ops, "d1")["feasible"], expected, mask)
