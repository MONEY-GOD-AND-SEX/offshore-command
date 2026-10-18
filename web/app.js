'use strict';
let snapshot;
let attendance;
let closed = false;
const $ = id => document.getElementById(id);
const node = (tag, value, className) => {
  const element = document.createElement(tag);
  if (value !== undefined) element.textContent = value;
  if (className) element.className = className;
  return element;
};
function render() {
  const stations = snapshot.report.stations.map(station => {
    const present = Object.values(attendance).filter(value => value === station.station).length;
    return {...station, present, deficit: Math.max(0, station.minimum - present)};
  });
  const total = snapshot.crew.length;
  const present = Object.keys(attendance).length;
  const deficits = stations.reduce((sum, station) => sum + station.deficit, 0);
  const ready = present === total && deficits === 0;
  $('metrics').replaceChildren();
  for (const [label, value, detail] of [['CREW ON BOARD', total, 'Synthetic vessel manifest'], ['ACCOUNTED FOR', `${present} / ${total}`, `${Math.round(present / total * 100)}% attendance`], ['STAFFING DEFICIT', deficits, 'Qualified arrivals still needed'], ['ENGINE AUDIT', snapshot.audit_valid ? 'PASS' : 'FAIL', `${snapshot.audit.length} hash-linked events`]]) {
    const card = node('article', undefined, 'metric');
    card.append(node('div', label, 'eyebrow'), node('strong', value), node('p', detail));
    $('metrics').append(card);
  }
  $('station-grid').replaceChildren();
  for (const station of stations) {
    const card = node('article', undefined, 'station');
    const top = node('div', undefined, 'station-top');
    top.append(node('h3', `Station ${station.station}`), node('span', station.deficit ? 'STAFFING GAP' : 'MINIMUM MET', station.deficit ? 'warning' : 'success'));
    const count = node('span', station.present, 'count');
    count.append(node('small', ` / ${station.capacity} capacity`));
    const bar = node('div', undefined, 'bar');
    const fill = node('span');
    fill.style.width = `${station.present / station.capacity * 100}%`;
    bar.append(fill);
    card.append(top, count, bar, node('p', `BST required · Minimum ${station.minimum} · Deficit ${station.deficit}`));
    $('station-grid').append(card);
  }
  const query = $('search').value.toLowerCase();
  $('crew-rows').replaceChildren();
  for (const person of snapshot.crew.filter(person => `${person.name} ${person.id} ${person.role}`.toLowerCase().includes(query))) {
    const row = node('tr');
    const name = node('td', person.name);
    name.append(node('small', person.id));
    row.append(name, node('td', person.role), node('td', attendance[person.id] || `Proposed: ${snapshot.plan.assignments[person.id] || 'Unassigned'}`), node('td', attendance[person.id] ? 'Accounted for' : 'Awaiting arrival', attendance[person.id] ? 'success' : 'warning'));
    $('crew-rows').append(row);
  }
  if (!$('crew-rows').children.length) {
    const cell = node('td', 'No crew match your search.');
    cell.colSpan = 4;
    const row = node('tr'); row.append(cell); $('crew-rows').append(row);
  }
  $('drill-state').textContent = closed ? 'SANDBOX CLOSED' : 'SANDBOX ACTIVE';
  $('close-drill').disabled = !ready || closed;
  $('apply-plan').disabled = closed || !snapshot.plan.feasible || ready;
  $('reset').disabled = false;
}
async function start() {
  try {
    const response = await fetch('./snapshot.json', {cache: 'no-store'});
    if (!response.ok) throw new Error(`Snapshot request failed (${response.status})`);
    snapshot = await response.json();
    attendance = {...snapshot.plan.fixed};
    $('audit-summary').textContent = `${snapshot.audit_valid ? 'Hash chain verified by the Python engine at build time.' : 'Audit verification failed.'} Training scenario: ${snapshot.scenario_at}. Build: ${new Date(snapshot.generated_at).toISOString()}. Sandbox changes are excluded from this audit and export.`;
    for (const event of [...snapshot.audit].reverse()) {
      const item = node('li', `${String(event.seq).padStart(3, '0')}  ${event.kind}`);
      item.append(node('span', `${event.actor} · ${event.digest.slice(0, 16)}…`));
      $('events').append(item);
    }
    $('apply-plan').onclick = () => {attendance = {...snapshot.plan.assignments}; $('status').textContent = 'Allocation applied in this tab. All arrivals are simulated.'; render();};
    $('close-drill').onclick = () => {closed = true; $('status').textContent = 'Sandbox drill closed. No operational database was changed.'; render();};
    $('reset').onclick = () => {attendance = {...snapshot.plan.fixed}; closed = false; $('status').textContent = 'Training sandbox reset to the engine snapshot.'; render();};
    $('search').oninput = render;
    $('download').disabled = false;
    $('download').onclick = () => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot, null, 2)], {type: 'application/json'}));
      const link = node('a'); link.href = url; link.download = 'offshore-engine-snapshot.json'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
    $('status').textContent = 'Engine snapshot loaded. Explore the allocation in the training sandbox.';
    render();
  } catch (error) {
    $('status').textContent = `Unable to load the workspace: ${error.message}. Please reload or check the deployment.`;
  }
}
start();
