export type ProfileId = 'pm' | 'engineer' | 'stakeholder';

export interface Profile {
  id: ProfileId;
  name: string;
  does: string;
  brief: string;
  start: string[];
  prompt: string;
}

export const profiles: Profile[] = [
  {
    id: 'pm',
    name: 'Product managers',
    does: 'Turn an idea into a board of ready stories, with research and a red team behind every requirement.',
    brief:
      'The product-team bundle is yours: it takes a raw idea through research, a PRD and a red team, then pushes stories to the board. Between initiatives, triage and acceptance criteria keep incoming work honest, and teammate answers how the product works today without you reading code.',
    start: ['kura add product-team --type bundle'],
    prompt: '/0-refine-idea A shared shopping list that works offline',
  },
  {
    id: 'engineer',
    name: 'Engineers',
    does: 'Build, fix and ship. Add a seat for each layer you own, and your agent hands every slice to the right one.',
    brief:
      'Start with the skills scout finds for your stack, then add a bundle for each layer you own. Small changes go straight to a seat; work across layers goes through feature-team, where you approve the spec before anything is built.',
    start: ['kura scout --add', 'kura add frontend backend qa --type bundle'],
    prompt: '/feature-team PROJ-412 Let customers export invoices as CSV',
  },
  {
    id: 'stakeholder',
    name: 'Stakeholders',
    does: 'Leads, founders, design and partner teams. Decide what is worth building and follow it, without running the pipeline.',
    brief:
      'Gates can reach you as pull requests and specs as files, so you may never install anything. If you want to ask questions yourself, restore the project’s set: the status board says where every initiative stands, and teammate explains what the product does.',
    start: ['kura restore'],
    prompt: '/product-lead status',
  },
];

export interface Cell {
  text: string;
  gate?: string;
}

export interface Stage {
  name: string;
  cells: Partial<Record<ProfileId, Cell>>;
}

export const stages: Stage[] = [
  {
    name: 'Idea',
    cells: {
      pm: { text: '/0-refine-idea turns it into a brief' },
      stakeholder: { gate: 'Gate 0', text: 'Is it worth building?' },
    },
  },
  {
    name: 'Requirements',
    cells: {
      pm: { text: '/1-research and /2-write-prd, then /3-red-team attacks it' },
      stakeholder: { gate: 'Gate 1', text: 'Are these the right requirements?' },
    },
  },
  {
    name: 'Design',
    cells: {
      pm: { text: '/4-tech-shape writes the UX spec and design doc' },
      engineer: { text: 'Reviews the design doc and ADRs as code owner' },
    },
  },
  {
    name: 'Stories',
    cells: {
      pm: { text: '/5-decompose to /7-push-to-board' },
      engineer: { text: 'Picks up ready stories from the board' },
    },
  },
  {
    name: 'Build',
    cells: {
      pm: { text: 'Hands a ready story to /feature-team' },
      engineer: { gate: 'Spec', text: '/feature-team, approving the spec before seats build' },
    },
  },
  {
    name: 'Review and ship',
    cells: {
      engineer: { text: '/code-review, then /ship' },
    },
  },
  {
    name: 'After it ships',
    cells: {
      pm: { text: '/8-living-spec records what now exists' },
      engineer: { text: '/watch sentry for new errors' },
      stakeholder: { text: 'Reads docs/specs/ and docs/LEARNINGS.md' },
    },
  },
  {
    name: 'Any time',
    cells: {
      pm: { text: '/teammate, /triage, /ac' },
      engineer: { text: '/teammate, /triage, /to-plan' },
      stakeholder: { text: '/product-lead status, /teammate' },
    },
  },
];
