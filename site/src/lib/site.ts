export const links = {
  catalog: 'https://github.com/jmanuelrosa/agent-catalog',
  kura: 'https://github.com/jmanuelrosa/kura',
  github: 'https://github.com',
};

export const upstreamUrl = (repo: string, commit: string) => `${links.github}/${repo}/tree/${commit}`;
