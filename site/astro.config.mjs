import { defineConfig } from 'astro/config';

export default defineConfig({
  server: {
    port: 32646,
    allowedHosts: ['agent-catalog.localhost'],
  },
  vite: {
    server: {
      strictPort: true,
    },
  },
});
