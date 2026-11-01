import { agents, bundles, type Agent, type Bundle } from './catalog';

const SEAT_SUFFIX = '-staff-engineer';
const SETUP_REVIEWER_SUFFIX = '-staff-reviewer';
const WRITING_TOOLS = ['Write', 'Edit', 'NotebookEdit', 'Bash'];

const areaLayout = [
  { name: 'Build the product', seats: ['frontend', 'design', 'backend', 'mobile', 'desktop'] },
  { name: 'Store and model data', seats: ['database', 'data', 'analytics'] },
  { name: 'Ship and run it', seats: ['platform', 'cloud', 'sre', 'dx'] },
  { name: 'Get found and measured', seats: ['seo', 'gtm'] },
  { name: 'Test and secure it', seats: ['qa', 'security'] },
];

export interface Segment {
  text: string;
  seat?: string;
}

export interface Seat {
  bundle: Bundle;
  agent: Agent;
  notFor: Segment[];
}

const isSeat = (bundle: Bundle) => bundle.agents.some((name) => name.endsWith(SEAT_SUFFIX));
const seatBundles = bundles.filter(isSeat);
const seatNames = new Set(seatBundles.map((bundle) => bundle.name));

const placed = areaLayout.flatMap((area) => area.seats);
const unplaced = [...seatNames].filter((name) => !placed.includes(name));
const unknown = placed.filter((name) => !seatNames.has(name));
if (unplaced.length || unknown.length) {
  throw new Error(`site/src/lib/team.ts areas are out of date. Unplaced: ${unplaced.join(', ') || 'none'}. Unknown: ${unknown.join(', ') || 'none'}.`);
}

function splitNotFor(text: string | undefined): Segment[] {
  if (!text) return [];
  return text.split(/\(([^)]+)\)/).map((part, index) =>
    index % 2 === 1 && seatNames.has(part) ? { text: part, seat: part } : { text: index % 2 === 1 ? `(${part})` : part },
  );
}

function toSeat(bundle: Bundle): Seat {
  const agent = agents.find((candidate) => candidate.bundle === bundle.name && candidate.name.endsWith(SEAT_SUFFIX));
  if (!agent) throw new Error(`The ${bundle.name} bundle has no staff-engineer agent.`);
  return { bundle, agent, notFor: splitNotFor(bundle.notFor) };
}

export const areas = areaLayout.map((area) => ({
  name: area.name,
  seats: area.seats.map((name) => toSeat(seatBundles.find((bundle) => bundle.name === name)!)),
}));

const standalone = agents.filter((agent) => !agent.bundle);
export const routers = standalone.filter((agent) => !agent.name.endsWith(SETUP_REVIEWER_SUFFIX));
export const setupReviewers = standalone.filter((agent) => agent.name.endsWith(SETUP_REVIEWER_SUFFIX));

export const crews = bundles
  .filter((bundle) => !isSeat(bundle))
  .map((bundle) => ({ bundle, agents: agents.filter((agent) => agent.bundle === bundle.name) }));

export const seatCount = seatBundles.length;

export const isReadOnly = (agent: Agent) => !!agent.tools && !agent.tools.some((tool) => WRITING_TOOLS.includes(tool));

export function leadSentences(text: string, count: number): string {
  return (text.match(/[^.!?]+[.!?]+(\s|$)/g) ?? [text]).slice(0, count).join('').trim();
}

export const searchText = (...parts: string[]) => parts.join(' ').toLowerCase();
