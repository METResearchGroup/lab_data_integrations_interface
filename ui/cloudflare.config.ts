import { bindings, defineConfig, defineWorker } from "cf/config";

// proxy.ts and the server components read process.env at request time.
// nodejs_compat on this compatibility date copies text bindings into
// process.env. The browser bundle still inlines the same names at build
// time, so deploy must set them in the environment before this file loads.
function publicText(name: string) {
	const value = process.env[name];
	if (typeof value !== "string" || value.length === 0) {
		throw new Error(
			`${name} is unset. npm run deploy:vinext loads it before this file is read.`,
		);
	}
	return bindings.text(value);
}

export default defineConfig({
	worker: defineWorker({
		name: "ldi-ui-preview",
		entrypoint: "vinext/server/fetch-handler",
		compatibilityDate: "2026-10-23",
		compatibilityFlags: ["nodejs_compat"],
		workersDev: true,
		observability: {
			enabled: true,
			logs: {
				enabled: true,
				headSamplingRate: 1,
				persist: false,
				destinations: ["ldi-preview-grafana-logs"],
			},
			traces: {
				enabled: true,
				headSamplingRate: 1,
				persist: false,
				destinations: ["ldi-preview-grafana-traces"],
			},
		},
		assets: {
			htmlHandling: "none",
			notFoundHandling: "none",
			runWorkerFirst: ["/*", "!/_next/static/*", "!/*/_next/static/*"],
		},
		env: {
			ASSETS: bindings.assets(),
			IMAGES: bindings.images(),
			// Keep this in step with NEXT_PUBLIC_API_URL in the build environment
			// (ui/src/lib/api.ts).
			NEXT_PUBLIC_API_URL: bindings.text(
				"https://ldi-api-preview.mind-technology-lab.workers.dev",
			),
			NEXT_PUBLIC_SUPABASE_URL: publicText("NEXT_PUBLIC_SUPABASE_URL"),
			NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: publicText(
				"NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
			),
		},
	}),
});
