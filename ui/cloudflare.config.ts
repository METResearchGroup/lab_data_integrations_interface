import { bindings, defineConfig, defineWorker } from "cf/config";

export default defineConfig({
  worker: defineWorker({
    name: "ldi-ui-preview",
    entrypoint: "vinext/server/fetch-handler",
    compatibilityDate: "2026-10-23",
    compatibilityFlags: ["nodejs_compat"],
    workersDev: true,
    observability: {
      enabled: true,
      logs: { enabled: true, headSamplingRate: 1, persist: true },
      traces: { enabled: true, headSamplingRate: 1, persist: true },
    },
    assets: {
      htmlHandling: "none",
      notFoundHandling: "none",
      runWorkerFirst: ["/*", "!/_next/static/*", "!/*/_next/static/*"],
    },
    env: {
      ASSETS: bindings.assets(),
      IMAGES: bindings.images(),
      // Public API origin. The browser bundle still reads this from
      // NEXT_PUBLIC_API_URL at build time (ui/src/lib/api.ts). Keep the two
      // in step. Supabase settings are build-time only and are not committed.
      NEXT_PUBLIC_API_URL: bindings.text(
        "https://ldi-api-preview.mind-technology-lab.workers.dev",
      ),
    },
  }),
});
