import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { basename, join, resolve } from 'node:path';

const root = resolve(process.env.CATALOG_ROOT ?? join(process.cwd(), '..'));

type Frontmatter = Record<string, string>;

export type Provenance = 'local' | 'upstream';

export interface Skill {
  name: string;
  description: string;
  groups: string[];
  provenance: Provenance;
  source?: string;
  commit?: string;
  updatedAt?: string;
  license?: string;
  bundle?: string;
  global: boolean;
  dependencyOnly: boolean;
  usedBy: string[];
}

export interface Agent {
  name: string;
  description: string;
  bundle?: string;
  model?: string;
  effort?: string;
  tools?: string[];
}

export interface Bundle {
  name: string;
  description: string;
  job: string;
  notFor?: string;
  groups: string[];
  agents: string[];
  skills: string[];
  requires: string[];
  checklists: string[];
}

export interface UpstreamSource {
  repo: string;
  commit: string;
  skills: string[];
  license?: string;
  licenseNote?: string;
}

export interface DerivedSource {
  skill: string;
  source: string;
  url: string;
  license: string;
}

interface Licenses {
  upstream?: Record<string, { license?: string | null; note?: string }>;
  derived?: Record<string, { source: string; url: string; license: string }>;
}

function loadLicenses(): Licenses {
  const path = join(root, 'licenses.json');
  return existsSync(path) ? (JSON.parse(readFileSync(path, 'utf8')) as Licenses) : {};
}

function unquote(value: string): string {
  const trimmed = value.trim();
  const quote = trimmed[0];
  if ((quote === '"' || quote === "'") && trimmed.endsWith(quote)) {
    return trimmed.slice(1, -1).replace(/\\"/g, '"').replace(/''/g, "'");
  }
  return trimmed;
}

export function parseFrontmatter(source: string): Frontmatter {
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!match?.[1]) return {};
  const lines = match[1].split(/\r?\n/);
  const result: Frontmatter = {};
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? '';
    const pair = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (!pair) continue;
    const [, key = '', rest = ''] = pair;
    const continuation: string[] = [];
    while (i + 1 < lines.length && /^(\s+|$)/.test(lines[i + 1] ?? '') && (lines[i + 1] ?? '').trim() !== '---') {
      continuation.push((lines[++i] ?? '').trim());
    }
    const block = /^[>|][+-]?$/.test(rest.trim());
    const parts = block ? continuation : [rest, ...continuation];
    result[key] = unquote(parts.filter(Boolean).join(' '));
  }
  return result;
}

function readFrontmatter(path: string): Frontmatter {
  return existsSync(path) ? parseFrontmatter(readFileSync(path, 'utf8')) : {};
}

function readJson<T>(file: string): T {
  return JSON.parse(readFileSync(join(root, file), 'utf8')) as T;
}

function listDir(path: string): string[] {
  return existsSync(path) ? readdirSync(path).filter((entry) => !entry.startsWith('.')).sort() : [];
}

interface RegistryEntry {
  name?: string;
  upstream_path?: string;
  groups?: string[];
  global?: boolean;
  dependency_only?: boolean;
  dependencies?: string[];
  updated_at?: string;
  note?: string;
}

interface Registry {
  upstream: Record<string, { commit: string; skills: RegistryEntry[] }>;
  local: RegistryEntry[];
}

const NOT_FOR = 'Not for:';

function checklistTitles(references: string): string[] {
  return listDir(references)
    .filter((file) => file.endsWith('.md'))
    .map((file) => readFileSync(join(references, file), 'utf8').match(/^# (.+)$/m)?.[1] ?? basename(file, '.md'));
}

function loadBundles(): Bundle[] {
  const registry = readJson<{ local: { name: string; groups: string[] }[] }>('bundle-registry.json');
  return registry.local.map(({ name, groups }) => {
    const dir = join(root, 'bundles', name);
    const manifest = JSON.parse(readFileSync(join(dir, 'bundle.json'), 'utf8')) as {
      description?: string;
      requires?: { skills?: string[] };
    };
    const description = manifest.description ?? '';
    const [job, notFor] = description.split(NOT_FOR);
    return {
      name,
      groups,
      description,
      job: job.trim(),
      notFor: notFor?.trim(),
      agents: listDir(join(dir, 'agents')).map((file) => basename(file, '.md')),
      skills: listDir(join(dir, 'skills')),
      requires: manifest.requires?.skills ?? [],
      checklists: listDir(join(dir, 'skills')).flatMap((skill) => checklistTitles(join(dir, 'skills', skill, 'references'))),
    };
  });
}

function loadSkills(bundles: Bundle[]): Skill[] {
  const registry = readJson<Registry>('skill-registry.json');
  const skills: Skill[] = [];

  for (const [repo, { commit, skills: entries }] of Object.entries(registry.upstream)) {
    for (const entry of entries) {
      const name = entry.name ?? basename(entry.upstream_path ?? '');
      const fm = readFrontmatter(join(root, 'skills', name, 'SKILL.md'));
      skills.push({
        name,
        description: fm.description ?? '',
        groups: entry.groups ?? [],
        provenance: 'upstream',
        source: repo,
        commit,
        updatedAt: entry.updated_at,
        license: fm.license,
        global: entry.global ?? false,
        dependencyOnly: entry.dependency_only ?? false,
        usedBy: [],
      });
    }
  }

  for (const entry of registry.local) {
    const name = entry.name ?? '';
    const fm = readFrontmatter(join(root, 'skills', name, 'SKILL.md'));
    skills.push({
      name,
      description: fm.description ?? '',
      groups: entry.groups ?? [],
      provenance: 'local',
      global: entry.global ?? false,
      dependencyOnly: entry.dependency_only ?? false,
      usedBy: [],
    });
  }

  for (const bundle of bundles) {
    for (const name of bundle.skills) {
      const fm = readFrontmatter(join(root, 'bundles', bundle.name, 'skills', name, 'SKILL.md'));
      skills.push({
        name,
        description: fm.description ?? '',
        groups: bundle.groups,
        provenance: 'local',
        bundle: bundle.name,
        global: false,
        dependencyOnly: false,
        usedBy: [],
      });
    }
  }

  const entries = [...Object.values(registry.upstream).flatMap(({ skills: upstream }) => upstream), ...registry.local];
  for (const entry of entries) {
    const parent = entry.name ?? basename(entry.upstream_path ?? '');
    for (const dependency of entry.dependencies ?? []) {
      skills.find((skill) => skill.name === dependency && !skill.bundle)?.usedBy.push(parent);
    }
  }

  return skills.sort((a, b) => a.name.localeCompare(b.name));
}

function readAgent(path: string, bundle?: string): Agent {
  const fm = readFrontmatter(path);
  return {
    name: basename(path, '.md'),
    description: fm.description ?? '',
    bundle,
    model: fm.model,
    effort: fm.effort,
    tools: fm.tools?.split(',').map((tool) => tool.trim()),
  };
}

function loadAgents(bundles: Bundle[]): Agent[] {
  const agents: Agent[] = listDir(join(root, 'agents'))
    .filter((file) => file.endsWith('.md'))
    .map((file) => readAgent(join(root, 'agents', file)));
  for (const bundle of bundles) {
    for (const name of bundle.agents) {
      agents.push(readAgent(join(root, 'bundles', bundle.name, 'agents', `${name}.md`), bundle.name));
    }
  }
  return agents.sort((a, b) => a.name.localeCompare(b.name));
}

function loadSources(skills: Skill[]): UpstreamSource[] {
  const licenses = loadLicenses().upstream ?? {};
  const bySource = new Map<string, UpstreamSource>();
  for (const skill of skills) {
    if (!skill.source || !skill.commit) continue;
    const source = bySource.get(skill.source) ?? {
      repo: skill.source,
      commit: skill.commit,
      skills: [],
      license: licenses[skill.source]?.license ?? undefined,
      licenseNote: licenses[skill.source]?.note,
    };
    source.skills.push(skill.name);
    bySource.set(skill.source, source);
  }
  return [...bySource.values()].sort((a, b) => b.skills.length - a.skills.length || a.repo.localeCompare(b.repo));
}

function loadDerived(): DerivedSource[] {
  return Object.entries(loadLicenses().derived ?? {}).map(([skill, entry]) => ({ skill, ...entry }));
}

export const bundles = loadBundles();
export const derived = loadDerived();
export const skills = loadSkills(bundles);
export const agents = loadAgents(bundles);
export const sources = loadSources(skills);

export const stats = {
  skills: skills.length,
  local: skills.filter((skill) => skill.provenance === 'local').length,
  upstream: skills.filter((skill) => skill.provenance === 'upstream').length,
  sources: sources.length,
  agents: agents.length,
  bundles: bundles.length,
};

export function firstSentence(text: string): string {
  const sentence = text.match(/^.*?[.!?](\s|$)/)?.[0] ?? text;
  return sentence.trim();
}

export function skillByName(name: string): Skill | undefined {
  return skills.find((skill) => skill.name === name);
}
