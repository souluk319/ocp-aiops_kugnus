import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const gatewayOrigin = env.AIOPS_GATEWAY_ORIGIN || 'http://127.0.0.1:18080';
  const devBearerToken = env.AIOPS_DEV_OPENSHIFT_TOKEN || '';

  return {
    plugins: [react()],
    server: {
      port: Number(env.AIOPS_PORTAL_PORT || 5173),
      proxy: {
        '/v1': {
          target: gatewayOrigin,
          changeOrigin: true,
          headers: devBearerToken
            ? {
                Authorization: `Bearer ${devBearerToken}`,
              }
            : undefined,
        },
      },
    },
  };
});
