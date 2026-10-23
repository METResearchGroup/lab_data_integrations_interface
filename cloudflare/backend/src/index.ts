import { Container } from "@cloudflare/containers";

const PORT = 8000;

// Names the container process reads with os.getenv / load_dotenv / EnvVarsContainer.
// Wrangler secrets and vars land on the Worker. This list copies the ones that
// are actually set into the container environment at start. Empty values are
// omitted so an unset ORIGIN_SECRET stays unset and the middleware stays open.
const FORWARDED = [
	"AWS_ACCESS_KEY_ID",
	"AWS_SECRET_ACCESS_KEY",
	"AWS_SESSION_TOKEN",
	"OPENAI_API_KEY",
	"GMAIL_SENDER_EMAIL",
	"GMAIL_APP_PASSWORD",
	"SUPABASE_URL",
	"ORIGIN_SECRET",
	"OTEL_EXPORTER_OTLP_HEADERS",
	"OTEL_RESOURCE_ATTRIBUTES",
	"DEPLOYMENT_ENVIRONMENT",
	"MAIL_TEST_RECIPIENT",
] as const;

export interface Env {
	API_CONTAINER: DurableObjectNamespace<ApiContainer>;
	CORS_ORIGINS: string;
	AWS_ACCESS_KEY_ID?: string;
	AWS_SECRET_ACCESS_KEY?: string;
	AWS_SESSION_TOKEN?: string;
	OPENAI_API_KEY?: string;
	GMAIL_SENDER_EMAIL?: string;
	GMAIL_APP_PASSWORD?: string;
	SUPABASE_URL?: string;
	ORIGIN_SECRET?: string;
	OTEL_EXPORTER_OTLP_HEADERS?: string;
	OTEL_RESOURCE_ATTRIBUTES?: string;
	DEPLOYMENT_ENVIRONMENT?: string;
	MAIL_TEST_RECIPIENT?: string;
}

export function containerEnv(env: Env): Record<string, string> {
	const vars: Record<string, string> = {
		PORT: String(PORT),
		CORS_ORIGINS: env.CORS_ORIGINS,
	};
	for (const name of FORWARDED) {
		const value = env[name];
		if (typeof value === "string" && value.length > 0) {
			vars[name] = value;
		}
	}
	return vars;
}

/**
 * One long-lived FastAPI process for the whole preview.
 *
 * getByName("api") pins every request to the same Durable Object, and
 * max_instances is 1, so the in-process rate limiter in backend/rate_limit.py
 * still sees every caller. The container sleeps after 30 minutes without a
 * proxied request. /query returns 202 and keeps working inside the process.
 * That background work does not reset the sleep timer. A query longer than
 * 30 minutes is stopped if no other request is proxied during the window.
 * There is no keep-warm cron.
 */
export class ApiContainer extends Container<Env> {
	defaultPort = PORT;
	sleepAfter = "30m";
	enableInternet = true;

	override async fetch(request: Request): Promise<Response> {
		await this.startAndWaitForPorts({
			ports: [PORT],
			startOptions: {
				envVars: containerEnv(this.env),
				enableInternet: true,
			},
			cancellationOptions: {
				// The helper's default is 20s, which is shorter than importing
				// this API image. First provision can take longer than a single
				// request; retry /health if this returns 500 while the instance
				// is still coming up.
				portReadyTimeoutMS: 180_000,
				instanceGetTimeoutMS: 120_000,
			},
		});
		return super.fetch(request);
	}
}

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		const container = env.API_CONTAINER.getByName("api");
		return container.fetch(request);
	},
} satisfies ExportedHandler<Env>;
