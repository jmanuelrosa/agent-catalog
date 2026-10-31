import { defineConfig } from 'astro/config';

import { devHostname } from './integrations/dev-hostname.ts';

export default defineConfig({
  output: 'static',
  integrations: [devHostname('agent-catalog.localhost')],
  server: {
    port: 32646,
  },
  vite: {
    server: {
      strictPort: true,
    },
  },
});
