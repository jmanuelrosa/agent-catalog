import type { AstroIntegration } from 'astro';
import type { ViteDevServer } from 'vite';

export function devHostname(hostname: string | undefined): AstroIntegration {
  let viteServer: ViteDevServer | undefined;

  return {
    name: 'dev-hostname',
    hooks: {
      'astro:server:setup': ({ server }) => {
        viteServer = server;
      },
      // Vite always names the loopback entry "localhost", and Astro prints the banner from these
      // URLs right after this hook, so this is the only seam that puts the custom name in it.
      // Deriving from the resolved URL keeps the real port when Vite falls back to another one.
      'astro:server:start': () => {
        const local = viteServer?.resolvedUrls?.local;
        const loopback = local?.[0];

        if (!hostname || !local || !loopback) return;

        const url = new URL(loopback);
        url.hostname = hostname;

        if (!local.includes(url.href)) local.unshift(url.href);
      },
    },
  };
}
