import type { ProfileId } from './profiles';

export type Size = 'skill' | 'agent' | 'bundle' | 'pipeline';

export interface Rung {
  size: Size;
  when: string;
  add: string;
  means: string;
  example: string;
}

export const ladder: Rung[] = [
  {
    size: 'skill',
    when: 'A question or a task inside one tool',
    add: 'One skill',
    means: 'Know-how your agent loads into its own context, only when the task matches.',
    example: 'vite',
  },
  {
    size: 'agent',
    when: 'A job better done in a clean room',
    add: 'One agent',
    means: 'A separate worker with its own context and tools. It returns a report and touches nothing it was not given.',
    example: 'architect',
  },
  {
    size: 'bundle',
    when: 'A discipline you own in this repo',
    add: 'A bundle',
    means: 'A staff seat plus the checklist it has to clear before it may say done.',
    example: 'frontend',
  },
  {
    size: 'pipeline',
    when: 'Work that crosses layers, or starts as an idea',
    add: 'A pipeline',
    means: 'Several seats coordinated for you, with you at the gates where a wrong call is expensive.',
    example: '/feature-team',
  },
];

export interface UseCase {
  id: string;
  need: string;
  for: ProfileId[];
  size: Size;
  setup: string[] | 'global';
  prompt: string;
  why: string;
  playbook?: string;
}

export interface Group {
  name: string;
  cases: UseCase[];
}

export const groups: Group[] = [
  {
    name: 'Understand',
    cases: [
      {
        id: 'unfamiliar-code',
        for: ['engineer', 'pm'],
        need: 'Understand code I did not write',
        size: 'skill',
        setup: 'global',
        prompt: '/teammate explain how refunds flow through services/payments',
        why: 'teammate is read-only and brings how, why and teach with it. You only ever call teammate.',
        playbook: 'understand',
      },
      {
        id: 'library-answer',
        for: ['engineer'],
        need: 'Get a current answer about a library I use',
        size: 'skill',
        setup: ['kura add vite --type skill'],
        prompt: 'Why is Vite re-optimizing dependencies on every start?',
        why: 'The skill is written by the people who maintain the tool, and it loads only for this question.',
        playbook: 'how',
      },
      {
        id: 'old-repo',
        for: ['engineer'],
        need: 'Find my way around a large, old repo',
        size: 'skill',
        setup: ['kura scout', 'kura scout --add'],
        prompt: '/teammate where would I start to change checkout?',
        why: 'scout reads your lockfiles and config, so the skills you get match the stack you actually run.',
        playbook: 'brownfield',
      },
      {
        id: 'diagram',
        for: ['engineer', 'pm'],
        need: 'Draw a diagram that stays true to the code',
        size: 'skill',
        setup: 'global',
        prompt: '/diagram the checkout flow, from cart to payment confirmation',
        why: 'Each diagram is anchored to the files it reflects, so it can be flagged when they change.',
      },
    ],
  },
  {
    name: 'Plan',
    cases: [
      {
        id: 'idea',
        for: ['pm'],
        need: 'Turn a rough idea into stories worth building',
        size: 'pipeline',
        setup: ['kura add product-team --type bundle'],
        prompt: '/0-refine-idea A shared shopping list that works offline',
        why: 'Research, a PRD and a red team come before any engineer, and you decide at two gates.',
        playbook: 'greenfield',
      },
      {
        id: 'grill',
        for: ['pm', 'engineer'],
        need: 'Stress-test a plan before I commit to it',
        size: 'skill',
        setup: 'global',
        prompt: '/grill-with-docs move sessions from cookies to JWTs',
        why: 'An interview that does not let a vague answer through, writing ADRs and a glossary as it goes.',
      },
      {
        id: 'plan',
        for: ['engineer'],
        need: 'Plan a refactor before touching the code',
        size: 'skill',
        setup: 'global',
        prompt: '/to-plan split billing out of the monolith',
        why: 'Research, then questions, then a plan in docs/plans/ that a person or a seat can pick up.',
      },
      {
        id: 'acceptance',
        for: ['pm', 'engineer'],
        need: 'Agree what done means for a ticket',
        size: 'skill',
        setup: 'global',
        prompt: '/ac PROJ-412',
        why: 'Acceptance criteria are written next to the code first, then published to the ticket as one comment.',
      },
      {
        id: 'ux',
        for: ['pm'],
        need: 'Pin down every screen and every state before UI work',
        size: 'agent',
        setup: 'global',
        prompt: 'Ask ux-shaper for a UX spec of docs/prd/shared-lists.md',
        why: 'It reads your design system without editing it, and lists empty, error, offline and no-permission states.',
      },
      {
        id: 'design',
        for: ['engineer'],
        need: 'Get a technical design, with the hard choices written down',
        size: 'agent',
        setup: 'global',
        prompt: 'Ask the architect to design invoice export from the brief',
        why: 'It writes a spec with one owner per slice, and an ADR for each choice that is hard to undo.',
      },
    ],
  },
  {
    name: 'Decide and follow along',
    cases: [
      {
        id: 'gate',
        for: ['stakeholder', 'pm'],
        need: 'Approve or stop an initiative at its gate',
        size: 'pipeline',
        setup: ['kura restore'],
        prompt: '/product-lead what is waiting on my decision?',
        why: 'Gate 0 asks whether it is worth building, Gate 1 whether the requirements are right. Your reason is recorded next to your name.',
        playbook: 'greenfield',
      },
      {
        id: 'status',
        for: ['stakeholder', 'pm'],
        need: 'See where every initiative stands',
        size: 'skill',
        setup: ['kura restore'],
        prompt: '/product-lead status',
        why: 'It reads the files each stage leaves behind, so the status cannot drift from the work, and it names the next command.',
      },
      {
        id: 'product-today',
        for: ['stakeholder', 'pm'],
        need: 'Know what the product does today, without reading code',
        size: 'skill',
        setup: 'global',
        prompt: '/teammate what happens at checkout when a payment fails?',
        why: 'teammate answers from the code and labels every claim by its evidence. What has shipped is also written down in docs/specs/.',
      },
    ],
  },
  {
    name: 'Build',
    cases: [
      {
        id: 'ui',
        for: ['engineer'],
        need: 'Build UI that respects our design system',
        size: 'bundle',
        setup: ['kura add frontend --type bundle'],
        prompt: 'Add a newsletter signup form to the footer',
        why: 'Your agent hands the work to the frontend seat, which reuses your components and clears its checklist.',
      },
      {
        id: 'schema',
        for: ['engineer'],
        need: 'Change a database schema without a bad night',
        size: 'bundle',
        setup: ['kura add database --type bundle'],
        prompt: 'Add a currency column to invoices and backfill it',
        why: 'The seat plans the migration in safe steps and backs index choices with EXPLAIN output.',
      },
      {
        id: 'infra',
        for: ['engineer'],
        need: 'Write infrastructure as code that nobody applies by accident',
        size: 'bundle',
        setup: ['kura add cloud --type bundle'],
        prompt: 'Add a private bucket for invoice exports in Terraform',
        why: 'The cloud seat writes and plans. Applying is always left to a person.',
      },
      {
        id: 'ci',
        for: ['engineer'],
        need: 'Set up CI or a Dockerfile',
        size: 'bundle',
        setup: ['kura add platform --type bundle'],
        prompt: 'Run the end-to-end suite on every pull request',
        why: 'The platform seat owns pipelines and images, and never deploys.',
      },
      {
        id: 'feature',
        for: ['engineer', 'pm'],
        need: 'Ship a feature that touches the API, the database and the UI',
        size: 'pipeline',
        setup: ['kura add frontend backend database qa --type bundle'],
        prompt: '/feature-team PROJ-412 Let customers export invoices as CSV',
        why: 'One spec, one contract between slices, seats working in parallel, then two review rounds.',
        playbook: 'feature',
      },
    ],
  },
  {
    name: 'Fix',
    cases: [
      {
        id: 'prod-error',
        for: ['engineer'],
        need: 'Fix a production error at the cause',
        size: 'bundle',
        setup: ['kura add qa --type bundle'],
        prompt: '/triage PAYMENTS-3F2',
        why: 'triage pulls the trace from Sentry, then a failing test is written before anything changes.',
        playbook: 'bug',
      },
      {
        id: 'ticket',
        for: ['pm', 'engineer'],
        need: 'Decide what to do with a ticket I have not read yet',
        size: 'skill',
        setup: 'global',
        prompt: '/triage PROJ-501',
        why: 'It reads the code the ticket touches, then routes it: automate, spec, clarify or park.',
      },
      {
        id: 'flaky',
        for: ['engineer'],
        need: 'Find out why a test fails one run in ten',
        size: 'bundle',
        setup: ['kura add qa --type bundle'],
        prompt: 'The checkout end-to-end test is flaky, find the cause',
        why: 'The qa seat diagnoses the flake instead of adding a retry, and checks the assertions can actually fail.',
      },
      {
        id: 'load',
        for: ['engineer'],
        need: 'See whether my site holds up under traffic',
        size: 'skill',
        setup: ['kura add k6-perf-test-website --type skill'],
        prompt: 'Load test the staging site with 200 concurrent users',
        why: 'One skill from Grafana writes the k6 suite and its thresholds. No seat is needed to run it.',
      },
    ],
  },
  {
    name: 'Review and ship',
    cases: [
      {
        id: 'review',
        for: ['engineer'],
        need: 'Get a review before I open the pull request',
        size: 'skill',
        setup: 'global',
        prompt: '/code-review',
        why: 'Four severities, eight axes, at most three nits. A review reports; it never edits.',
      },
      {
        id: 'ship',
        for: ['engineer'],
        need: 'Commit, push and open the pull request in one go',
        size: 'skill',
        setup: 'global',
        prompt: '/ship',
        why: 'Conventional commits split by concern and a written PR description, after one confirmation.',
      },
    ],
  },
  {
    name: 'Run it in production',
    cases: [
      {
        id: 'slo',
        for: ['engineer'],
        need: 'Alerts that page for the right reasons',
        size: 'bundle',
        setup: ['kura add sre --type bundle'],
        prompt: 'Define an SLO for checkout and alert on burn rate',
        why: 'The sre seat writes SLOs, burn-rate alerts and the runbook each alert links to.',
      },
      {
        id: 'watch',
        for: ['engineer'],
        need: 'A regular report of new production errors',
        size: 'skill',
        setup: 'global',
        prompt: '/watch sentry',
        why: 'Meant to be scheduled. It writes one report and routes each error through triage; it files nothing.',
      },
    ],
  },
  {
    name: 'Get found',
    cases: [
      {
        id: 'search',
        for: ['pm', 'engineer'],
        need: 'Show up in search results and in AI answers',
        size: 'bundle',
        setup: ['kura add seo --type bundle', 'kura add ai-seo --type skill'],
        prompt: 'Find out why /pricing is not indexed and fix it',
        why: 'The seo seat checks the HTML a crawler actually receives, and never cloaks or fakes markup.',
      },
    ],
  },
  {
    name: 'Tune your setup',
    cases: [
      {
        id: 'prompts',
        for: ['engineer'],
        need: 'Stop approving the same harmless commands',
        size: 'skill',
        setup: 'global',
        prompt: '/cc-fewer-permission-prompts',
        why: 'It ranks the read-only commands you keep approving and adds only the ones you pick.',
      },
      {
        id: 'setup-review',
        for: ['engineer'],
        need: 'Find out what my agent setup is missing',
        size: 'agent',
        setup: 'global',
        prompt: '/setup-review',
        why: 'A reviewer agent reads current docs, then your settings, and returns ranked recommendations.',
      },
      {
        id: 'handoff',
        for: ['engineer', 'pm'],
        need: 'Carry a long session over to a fresh one',
        size: 'skill',
        setup: 'global',
        prompt: '/handoff',
        why: 'It compacts what matters into a document the next session can start from.',
      },
    ],
  },
];

export const caseCount = groups.reduce((total, group) => total + group.cases.length, 0);
