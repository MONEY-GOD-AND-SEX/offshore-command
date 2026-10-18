import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Conflict(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identifier(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError("Expected non-empty identifier of at most 128 characters")
    return value


class Operations:
    def __init__(self, path, clock=None):
        self.path = str(path)
        self.clock = clock or (lambda: int(time.time()))
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(Path(__file__).with_name("schema.sql").read_text())

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    def execute(self, actor, key, command, data):
        identifier(actor)
        identifier(key)
        if not isinstance(data, dict):
            raise ValueError("Command data must be an object")
        handlers = {
            "vessel.create": self._vessel,
            "crew.register": self._crew,
            "certificate.set": self._certificate,
            "station.configure": self._station,
            "drill.start": self._start,
            "drill.check_in": self._check_in,
            "drill.close": self._close,
        }
        if command not in handlers:
            raise ValueError("Unknown command")
        fingerprint = hashlib.sha256(canonical([actor, command, data]).encode()).hexdigest()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                old = db.execute("SELECT * FROM requests WHERE key=?", (key,)).fetchone()
                if old:
                    if old["digest"] != fingerprint:
                        raise Conflict("Idempotency key reused with different content")
                    db.commit()
                    return json.loads(old["result"])
                now = self.clock()
                result = handlers[command](db, data, now)
                self._event(db, now, actor, command, data)
                db.execute("INSERT INTO requests VALUES(?,?,?)", (key, fingerprint, canonical(result)))
                db.commit()
                return result
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise Conflict(str(exc)) from exc
            except Exception:
                db.rollback()
                raise

    def _vessel(self, db, data, now):
        vessel = identifier(data["vessel"])
        db.execute("INSERT INTO vessels VALUES(?)", (vessel,))
        return {"vessel": vessel}

    def _crew(self, db, data, now):
        crew, vessel, name = (identifier(data[k]) for k in ("crew", "vessel", "name"))
        db.execute("INSERT INTO crew VALUES(?,?,?)", (crew, vessel, name))
        return {"crew": crew}

    def _certificate(self, db, data, now):
        crew, kind = (identifier(data[k]) for k in ("crew", "certificate"))
        expires = data["expires"]
        if type(expires) is not int or expires <= now:
            raise ValueError("Certificate expiry must be a future Unix timestamp")
        db.execute("INSERT INTO certificates VALUES(?,?,?) ON CONFLICT(crew,kind) DO UPDATE SET expires=excluded.expires", (crew, kind, expires))
        return {"crew": crew, "certificate": kind, "expires": expires}

    def _station(self, db, data, now):
        vessel, station, certificate = (identifier(data[k]) for k in ("vessel", "station", "certificate"))
        minimum, capacity = data["minimum"], data["capacity"]
        if type(minimum) is not int or type(capacity) is not int or not 0 <= minimum <= capacity <= 10000:
            raise ValueError("Invalid staffing bounds")
        db.execute("INSERT INTO stations VALUES(?,?,?,?,?) ON CONFLICT(vessel,id) DO UPDATE SET minimum=excluded.minimum,capacity=excluded.capacity,certificate=excluded.certificate", (vessel, station, minimum, capacity, certificate))
        return {"station": station}

    def _start(self, db, data, now):
        drill, vessel = (identifier(data[k]) for k in ("drill", "vessel"))
        if not db.execute("SELECT 1 FROM stations WHERE vessel=?", (vessel,)).fetchone():
            raise Conflict("Configure at least one station")
        if not db.execute("SELECT 1 FROM crew WHERE vessel=?", (vessel,)).fetchone():
            raise Conflict("Register at least one crew member")
        db.execute("INSERT INTO drills VALUES(?,?,'active',?,NULL)", (drill, vessel, now))
        db.execute("INSERT INTO manifest SELECT ?,id FROM crew WHERE vessel=?", (drill, vessel))
        db.execute("INSERT INTO drill_stations SELECT ?,id,minimum,capacity,certificate FROM stations WHERE vessel=?", (drill, vessel))
        return {"drill": drill, "state": "active"}

    def _active(self, db, drill):
        row = db.execute("SELECT * FROM drills WHERE id=?", (identifier(drill),)).fetchone()
        if not row or row["state"] != "active":
            raise Conflict("Drill is not active")
        return row

    def _check_in(self, db, data, now):
        drill, crew, station = (identifier(data[k]) for k in ("drill", "crew", "station"))
        self._active(db, drill)
        config = db.execute("SELECT * FROM drill_stations WHERE drill=? AND id=?", (drill, station)).fetchone()
        if not config:
            raise Conflict("Station is outside the drill")
        if not db.execute("SELECT 1 FROM manifest WHERE drill=? AND crew=?", (drill, crew)).fetchone():
            raise Conflict("Crew member is outside the drill manifest")
        old = db.execute("SELECT station FROM attendance WHERE drill=? AND crew=?", (drill, crew)).fetchone()
        if old:
            if old["station"] != station:
                raise Conflict("Crew member is already assigned to another station")
            return {"crew": crew, "station": station, "duplicate": True}
        certificate = db.execute("SELECT expires FROM certificates WHERE crew=? AND kind=?", (crew, config["certificate"])).fetchone()
        if not certificate or certificate["expires"] <= now:
            raise Conflict("Required certificate is missing or expired")
        count = db.execute("SELECT COUNT(*) FROM attendance WHERE drill=? AND station=?", (drill, station)).fetchone()[0]
        if count >= config["capacity"]:
            raise Conflict("Station capacity reached")
        db.execute("INSERT INTO attendance VALUES(?,?,?,?)", (drill, crew, station, now))
        return {"crew": crew, "station": station, "duplicate": False}

    def _close(self, db, data, now):
        drill = identifier(data["drill"])
        active = self._active(db, drill)
        if now < active["started"]:
            raise Conflict("Clock precedes drill start")
        report = self._report(db, drill, now)
        if not report["ready"]:
            raise Conflict("Missing crew or staffing deficiencies prevent closure")
        db.execute("UPDATE drills SET state='closed',ended=? WHERE id=?", (now, drill))
        report["state"] = "closed"
        db.execute("INSERT INTO closed_reports VALUES(?,?)", (drill, canonical(report)))
        return {"drill": drill, "state": "closed", "elapsed_seconds": now - active["started"]}

    def _report(self, db, drill, now):
        final = db.execute("SELECT report FROM closed_reports WHERE drill=?", (identifier(drill),)).fetchone()
        if final:
            return json.loads(final[0])
        row = db.execute("SELECT * FROM drills WHERE id=?", (identifier(drill),)).fetchone()
        if not row:
            raise Conflict("Unknown drill")
        missing = [r[0] for r in db.execute("SELECT crew FROM manifest WHERE drill=? EXCEPT SELECT crew FROM attendance WHERE drill=? ORDER BY crew", (drill, drill))]
        stations = []
        for station in db.execute("SELECT * FROM drill_stations WHERE drill=? ORDER BY id", (drill,)):
            members = list(db.execute("SELECT a.crew,c.expires FROM attendance a LEFT JOIN certificates c ON c.crew=a.crew AND c.kind=? WHERE a.drill=? AND a.station=?", (station["certificate"], drill, station["id"])))
            evaluation = row["ended"] if row["ended"] is not None else now
            eligible = sum(r["expires"] is not None and r["expires"] > evaluation for r in members)
            stations.append({"station": station["id"], "present": len(members), "eligible": eligible, "minimum": station["minimum"], "capacity": station["capacity"], "deficit": max(0, station["minimum"] - eligible)})
        return {"drill": drill, "vessel": row["vessel"], "state": row["state"], "missing": missing, "stations": stations, "ready": not missing and all(s["deficit"] == 0 and s["eligible"] == s["present"] for s in stations)}

    def report(self, drill):
        with self.connection() as db:
            db.execute("BEGIN")
            return self._report(db, drill, self.clock())

    def _event(self, db, now, actor, kind, payload):
        last = db.execute("SELECT digest FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = last[0] if last else "0" * 64
        encoded = canonical(payload)
        digest = hashlib.sha256(canonical([now, actor, kind, encoded, previous]).encode()).hexdigest()
        db.execute("INSERT INTO events(at,actor,kind,payload,previous,digest) VALUES(?,?,?,?,?,?)", (now, actor, kind, encoded, previous, digest))

    def audit(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM events ORDER BY seq")]

    def verify(self):
        previous = "0" * 64
        for row in self.audit():
            digest = hashlib.sha256(canonical([row["at"], row["actor"], row["kind"], row["payload"], previous]).encode()).hexdigest()
            if row["previous"] != previous or row["digest"] != digest:
                return False
            previous = digest
        return True

    def backup(self, destination):
        if Path(destination).resolve() == Path(self.path).resolve():
            raise ValueError("Backup destination must differ from source")
        with self.connection() as source, sqlite3.connect(destination) as target:
            source.backup(target)
