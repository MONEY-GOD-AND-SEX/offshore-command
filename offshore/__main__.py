import argparse
import json
import sys

from .engine import Conflict, Operations


def main():
    parser = argparse.ArgumentParser(prog="offshore")
    parser.add_argument("--db", default="data/operations.sqlite3")
    sub = parser.add_subparsers(dest="action", required=True)
    execute = sub.add_parser("execute")
    execute.add_argument("command")
    execute.add_argument("payload", type=json.loads)
    execute.add_argument("--actor", required=True)
    execute.add_argument("--key", required=True)
    report = sub.add_parser("report")
    report.add_argument("drill")
    planner = sub.add_parser("plan")
    planner.add_argument("drill")
    sub.add_parser("audit")
    sub.add_parser("verify")
    backup = sub.add_parser("backup")
    backup.add_argument("destination")
    args = parser.parse_args()
    from pathlib import Path
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    operations = Operations(args.db)
    try:
        if args.action == "execute":
            result = operations.execute(args.actor, args.key, args.command, args.payload)
        elif args.action == "report":
            result = operations.report(args.drill)
        elif args.action == "plan":
            from .planner import plan
            result = plan(operations, args.drill)
        elif args.action == "audit":
            result = operations.audit()
        elif args.action == "verify":
            valid = operations.verify()
            print(json.dumps({"valid": valid}))
            return 0 if valid else 1
        else:
            operations.backup(args.destination)
            result = {"backup": args.destination}
        print(json.dumps(result, indent=2))
        return 0
    except (Conflict, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
