export interface Step {
  actor: string;
  kind: 'skill' | 'agent' | 'human' | 'kura';
  does: string;
}

export interface Playbook {
  id: string;
  label: string;
  situation: string;
  setup: string[];
  prompt: string;
  steps: Step[];
  outcome: string;
}

export const playbooks: Playbook[] = [
  {
    id: 'greenfield',
    label: 'Green field',
    situation:
      'An empty folder and an idea. The risk is not writing code too slowly; it is building the wrong thing quickly and locking in choices nobody made on purpose.',
    setup: ['kura init --harness claude --yes', 'kura add product-team --type bundle', 'kura add frontend backend --type bundle'],
    prompt: '/0-refine-idea A shared shopping list that works offline for a household',
    steps: [
      { actor: '0-refine-idea', kind: 'skill', does: 'Sharpens the idea and asks you to kill it or proceed. This is gate 0.' },
      { actor: '1-research … 3-red-team', kind: 'skill', does: 'Market, competitors and user evidence, a PRD, then a red team that attacks it. Gate 1 is yours.' },
      { actor: 'ux-shaper', kind: 'agent', does: 'Writes every screen and every state: empty list, offline, sync conflict, no permission.' },
      { actor: 'architect', kind: 'agent', does: 'Turns the brief into a spec with ADRs for the choices that are hard to undo, such as the sync model.' },
      { actor: '5-decompose → 7-push-to-board', kind: 'skill', does: 'Splits the spec into stories with acceptance criteria and pushes them to GitHub as epics and sub-issues.' },
    ],
    outcome:
      'A repo with a PRD, a design doc, ADRs and a board of ready stories. Nothing is built yet, and every irreversible choice has a written reason.',
  },
  {
    id: 'brownfield',
    label: 'Brown field',
    situation:
      'A five-year-old codebase with its own conventions, half-documented. An agent that does not know the house rules will happily invent a second design system next to the first.',
    setup: ['kura init --harness claude --yes', 'kura scout', 'kura scout --add'],
    prompt: '/teammate give me a map of this repo and where I would start to change checkout',
    steps: [
      { actor: 'kura scout', kind: 'kura', does: 'Reads package.json, lockfiles and config, then recommends skills with the evidence it found, such as react@19 in package.json.' },
      { actor: 'teammate', kind: 'skill', does: 'Acts as a read-only senior colleague: traces the checkout flow and labels each claim by the evidence behind it.' },
      { actor: 'how / why', kind: 'skill', does: 'Run by teammate, never by you: how walks the code path; why digs out the rationale from commits, ADRs and PRs.' },
      { actor: 'diagram', kind: 'skill', does: 'Draws the flow as Mermaid in your docs, anchored to the files it reflects so it can be flagged when it goes stale.' },
    ],
    outcome:
      'Skills matched to the stack you actually run, a map of the area you are about to change, and a diagram that stays honest.',
  },
  {
    id: 'feature',
    label: 'New feature',
    situation:
      'A ticket that touches the API, the database and the UI. One agent doing all three in one context window loses track; three agents without a shared contract collide.',
    setup: ['kura add frontend backend database qa --type bundle'],
    prompt: '/feature-team PROJ-412 Let customers export their invoices as CSV',
    steps: [
      { actor: 'triage', kind: 'skill', does: 'Reads the ticket and the code it touches, then routes it: automate, spec, clarify or park.' },
      { actor: 'architect', kind: 'agent', does: 'Writes docs/specs/invoice-export.md with an owner per slice and the exact contract between slices.' },
      { actor: 'You', kind: 'human', does: 'Approve the spec. Nothing is built before this gate.' },
      { actor: 'backend, database and frontend seats', kind: 'agent', does: 'Build their slices in parallel, each in its own git worktree, each checked against its failure-modes list.' },
      { actor: 'code-reviewer', kind: 'agent', does: 'Two read-only review rounds: the first returns fix briefs, the second only reports.' },
      { actor: 'ship', kind: 'skill', does: 'You run it: conventional commits and a PR description after one confirmation.' },
    ],
    outcome:
      'A reviewed PR built from an approved spec, plus an integration report that lists what each seat did and every decision it escalated.',
  },
  {
    id: 'bug',
    label: 'Fix a bug',
    situation:
      'Production throws an error you have never seen. The tempting fix is a try/catch around the symptom.',
    setup: ['kura add qa --type bundle', 'kura add test-driven-development --type skill'],
    prompt: '/triage PAYMENTS-3F2 (the Sentry short id)',
    steps: [
      { actor: 'sentry', kind: 'skill', does: 'Pulls the stack trace, breadcrumbs and the release it started in through the sentry CLI.' },
      { actor: 'triage', kind: 'skill', does: 'Decides whether the fix is small and clear (automate) or needs a spec, and drafts any reply without posting it.' },
      { actor: 'teammate', kind: 'skill', does: 'You ask it why the failing path changed; its why pass finds the commit or decision that introduced the regression.' },
      { actor: 'test-driven-development', kind: 'skill', does: 'Writes the failing test that reproduces the bug before anything is changed.' },
      { actor: 'owning seat', kind: 'agent', does: 'Fixes the cause and runs the checks; the qa failure-modes list catches assertions that would pass anyway.' },
    ],
    outcome: 'A fix with a test that failed before it and passes after it, and a written cause rather than a guess.',
  },
  {
    id: 'understand',
    label: 'Understand code',
    situation:
      'You have been handed an area you did not write and a deadline. Reading every file is slow; asking a chat window gives you confident fiction.',
    setup: ['kura sync   # teammate is global: it arrives with how, why and teach'],
    prompt: '/teammate explain the permissions model in services/auth',
    steps: [
      { actor: 'teammate', kind: 'skill', does: 'Acts as a read-only senior colleague and hands the question to the skills it brings, which you never call yourself.' },
      { actor: 'how', kind: 'skill', does: 'Walks the code: entry points, the call path, where data is shaped and where it is checked.' },
      { actor: 'why', kind: 'skill', does: 'Recovers the reasons from ADRs, commit messages and PR threads, and says when it found none.' },
      { actor: 'teach', kind: 'skill', does: 'Weaves both into one plain explanation pitched at what you already know.' },
    ],
    outcome: 'An explanation you can repeat to someone else, with every claim pointing at a file or a commit.',
  },
  {
    id: 'how',
    label: 'How does it work',
    situation:
      'A library or service you use every day behaves in a way you did not expect. Model training data is months old; the docs changed last week.',
    setup: ['kura add vite react-router --type skill'],
    prompt: 'How does Vite decide which dependencies to pre-bundle, and why is mine re-optimizing on every start?',
    steps: [
      { actor: 'vite', kind: 'skill', does: 'From antfu/skills, kept by a Vite core team member: current config, plugin API and the Rolldown migration, loaded only for this question.' },
      { actor: 'research', kind: 'skill', does: 'When the answer needs more, writes a short memo with every source cited.' },
    ],
    outcome: 'An answer grounded in the maintainers’ own guidance and your actual config, instead of a plausible paragraph from memory.',
  },
];
