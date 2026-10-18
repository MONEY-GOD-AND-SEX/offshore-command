# Offshore Command

Persistent offshore crew readiness and muster operations. Python 3.12+, SQLite, no external Python dependencies.

## Published workspace

[Open Offshore Command](https://money-god-and-sex.github.io/offshore-command/)

The responsive Pages dashboard includes crew search, station staffing and capacity, allocation simulation, closure guards, audit history and JSON export. Deployments execute the real Python/SQLite engine using synthetic training fixtures to produce the displayed snapshot.

Sandbox actions are held in memory in the current tab and reset on reload. They do not confirm physical attendance, write to SQLite or change the engine audit. Persistent operations use the CLI locally or in Codespaces. Pages does not host a Python server or an application database.

```sh
python scripts/build_pages.py dist
python -m http.server 8000 --directory dist
```

The Pages workflow tests the project before publishing. Repository Pages source must be **GitHub Actions**.

## Operations

- Register vessels, crew and certificate expiry dates.
- Define station qualifications, minimum staffing and capacity.
- Snapshot the manifest and station requirements when a drill starts.
- Reject cross-vessel attendance, expired qualifications and conflicting assignments.
- Serialize concurrent writers to prevent overbooking.
- Retry commands safely using request identifiers.
- Block closure until every manifest member is present and all staffing requirements are met.
- Retain closed reports, ordered audit events and consistent database backups.
- Plan qualified crew allocation using a minimum-cost maximum-flow solver while preserving actual check-ins.

## Run

```sh
python -m unittest discover -s tests -v
python -m offshore.demo
python -m offshore execute vessel.create '{"vessel":"vessel-1"}' --actor operator --key vessel-1-create
python -m offshore audit
python -m offshore verify
python -m offshore backup /tmp/operations-backup.sqlite3
```

The database defaults to `data/operations.sqlite3`. Use `--db PATH` before the subcommand to select another file. `python -m offshore --help` lists commands.

`python -m offshore plan DRILL_ID` proposes a staffing allocation. Planning is read-only: actual arrivals must be recorded separately. The solver maximizes assignments and prioritizes minimum staffing requirements. It reports unassigned crew, qualification gaps and expired fixed attendance.

## Workspace

Open `offshore-command.code-workspace` locally or create a Codespace from this repository. The dev container runs the test suite during setup. Each account creates its own Codespace and authenticates with its own GitHub session. Shared code belongs in Git; live crew records do not.

[Create a Codespace](https://codespaces.new/MONEY-GOD-AND-SEX/offshore-command)

SQLite runs inside the workspace and survives application restarts. It is not a GitHub-managed database. Deleting a Codespace deletes its local database; copy backups to durable storage before deletion. GitHub Pro usage is personal and subject to the account's remaining quota. The Developer Program does not provision a database. Actions artifacts contain test evidence only.

## Design

Every command acquires a SQLite `BEGIN IMMEDIATE` transaction. State changes, audit events and idempotency records commit together. WAL, full synchronization, foreign keys and unique constraints protect persistence. Read reports use a consistent transaction snapshot. Closed reports are stored at closure and do not change when certificates are renewed.

Audit hashes detect edits against an intact chain. They do not provide external attestation: a database administrator can replace the chain. SQLite triggers block ordinary event updates and deletes. The actor field records an operator label; it is not authentication. Local filesystem access defines the trust boundary.

## Evidence

`python -m offshore.demo` executes real database transactions and restores a backup using explicitly synthetic training input. [Recorded output](evidence/run.json). GitHub Actions reruns tests on Python 3.12 and 3.13 and uploads fresh execution evidence.

This implementation adds persistence, capacity enforcement, transactional retries, audit verification and frozen reports beyond the in-memory workflows in [OFS2X Offshore Operations](https://github.com/brunnojob/ofs2x-offshore-operations). It is an independent implementation. No original code or video was copied.

## Scope

Operator decision support. Not a certified safety system or a replacement for vessel emergency procedures. Certificate dates are operator-supplied; no external issuer validation is performed. Clocks must be synchronized. The CLI assumes trusted operators and is not a public network service.

## Contributions

This implementation was prepared with coding-assistant support at the owner's request. Submissions use the authorized `brunnojob` connection for the engine, workspace and deployment, and `ineedfoundmyway` for the planner and regression tests. Account submissions do not imply independent human review or volunteer authorship.

Read [CONTRIBUTING.md](CONTRIBUTING.md). MIT licensed.
