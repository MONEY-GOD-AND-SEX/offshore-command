from .engine import Operations, identifier


def plan(operations: Operations, drill: str):
    with operations.connection() as db:
        db.execute("BEGIN")
        operations._active(db, drill)
        now = operations.clock()
        stations = [dict(row) for row in db.execute("SELECT * FROM drill_stations WHERE drill=? ORDER BY id", (drill,))]
        crew = [row[0] for row in db.execute("SELECT crew FROM manifest WHERE drill=? ORDER BY crew", (drill,))]
        qualifications = {(row[0], row[1]) for row in db.execute("SELECT crew,kind FROM certificates WHERE expires>?", (now,))}
        fixed = {row[0]: row[1] for row in db.execute("SELECT crew,station FROM attendance WHERE drill=?", (drill,))}
    assigned = dict(fixed)
    pending = [person for person in crew if person not in fixed]
    graph = {}

    def edge(source, target, capacity, cost):
        graph.setdefault(source, [])
        graph.setdefault(target, [])
        forward = [target, capacity, cost, len(graph[target])]
        reverse = [source, 0, -cost, len(graph[source])]
        graph[source].append(forward)
        graph[target].append(reverse)
        return forward

    source, sink = ("source",), ("sink",)
    graph[source], graph[sink] = [], []
    choices = {}
    invalid = []
    for station in stations:
        name = station["id"]
        occupants = [person for person, current in fixed.items() if current == name]
        invalid.extend(person for person in occupants if (person, station["certificate"]) not in qualifications)
        needed = max(0, station["minimum"] - len(occupants))
        available = station["capacity"] - len(occupants)
        edge(("station", name), sink, needed, -1)
        edge(("station", name), sink, available - needed, 0)
    for person in pending:
        node = ("crew", person)
        edge(source, node, 1, 0)
        for station in stations:
            if (person, station["certificate"]) in qualifications:
                choices[person, station["id"]] = edge(node, ("station", station["id"]), 1, 0)
    while True:
        distances = {node: float("inf") for node in graph}
        distances[source] = 0
        parents = {}
        for _ in range(len(graph) - 1):
            changed = False
            for node, edges in graph.items():
                for index, (target, capacity, cost, _) in enumerate(edges):
                    if capacity > 0 and distances[node] + cost < distances[target]:
                        distances[target] = distances[node] + cost
                        parents[target] = node, index
                        changed = True
            if not changed:
                break
        if sink not in parents:
            break
        node = sink
        while node != source:
            previous, index = parents[node]
            selected = graph[previous][index]
            selected[1] -= 1
            graph[node][selected[3]][1] += 1
            node = previous
    for (person, station), selected in choices.items():
        if selected[1] == 0:
            assigned[person] = station
    deficits = {station["id"]: max(0, station["minimum"] - sum(current == station["id"] and (person, station["certificate"]) in qualifications for person, current in assigned.items())) for station in stations}
    unassigned = [person for person in crew if person not in assigned]
    return {"drill": identifier(drill), "assignments": assigned, "fixed": fixed, "unassigned": unassigned, "invalid_fixed": sorted(invalid), "deficits": deficits, "feasible": not unassigned and not invalid and not any(deficits.values())}
