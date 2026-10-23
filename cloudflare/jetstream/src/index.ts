import { Container } from "@cloudflare/containers";

// The image's CMD is uvicorn. This container replaces it at start.
const ENTRYPOINT = [
	"/app/.venv/bin/python",
	"-m",
	"bluesky_ingestion_jetstream.main",
];

// Names the process reads with os.getenv / load_dotenv. Empty values are
// omitted so an unset optional variable stays unset.
const FORWARDED = [
	"AWS_ACCESS_KEY_ID",
	"AWS_SECRET_ACCESS_KEY",
	"AWS_SESSION_TOKEN",
	"OTEL_EXPORTER_OTLP_HEADERS",
] as const;

// Image pull on the first start can take a few minutes. Each attempt polls
// one port. A process that never binds a port still counts as started when
// the runtime reports that the container is not listening and the instance
// is running. See @cloudflare/containers startContainerIfNotRunning.
const START_WINDOW_MS = 240_000;
const POLL_MS = 3_000;
const PORT_TO_CHECK = 8000;

const SUPERVISE_HEADER = "x-ldi-supervise";

export interface Env {
	JETSTREAM_CONTAINER: DurableObjectNamespace<JetstreamContainer>;
	JETSTREAM_ENABLED: string;
	AWS_ACCESS_KEY_ID?: string;
	AWS_SECRET_ACCESS_KEY?: string;
	AWS_SESSION_TOKEN?: string;
	OTEL_EXPORTER_OTLP_HEADERS?: string;
}

export function containerEnv(env: Env): Record<string, string> {
	const vars: Record<string, string> = {};
	for (const name of FORWARDED) {
		const value = env[name];
		if (typeof value === "string" && value.length > 0) {
			vars[name] = value;
		}
	}
	return vars;
}

function isUp(status: string): boolean {
	return status === "running" || status === "healthy";
}

/**
 * One Jetstream writer for the preview account.
 *
 * getByName("jetstream") and max_instances 1 keep a single process, which is
 * what the DynamoDB cursor assumes. sleepAfter is 30m, and the default
 * onActivityExpired would SIGTERM the process then, because nothing proxies
 * HTTP at it to reset the timer. The override below does not stop it.
 * A cron every minute restarts the process if it has exited, and stops it
 * when JETSTREAM_ENABLED is not "true".
 */
export class JetstreamContainer extends Container<Env> {
	sleepAfter = "30m";
	enableInternet = true;
	entrypoint = ENTRYPOINT;

	override async onActivityExpired(): Promise<void> {
		// Leave the process running. The base method calls stop().
		console.log("jetstream activity timer elapsed; leaving the process running");
	}

	override async fetch(request: Request): Promise<Response> {
		const url = new URL(request.url);
		if (request.method === "GET" && url.pathname === "/status") {
			return Response.json(await this.statusBody());
		}
		if (request.method === "POST" && url.pathname === "/supervise") {
			if (request.headers.get(SUPERVISE_HEADER) !== "1") {
				return new Response("Not found", { status: 404 });
			}
			await this.supervise();
			return new Response("ok");
		}
		return new Response("Not found", { status: 404 });
	}

	private platformRunning(): boolean {
		const runtime = this as unknown as { container?: { running?: boolean } };
		return runtime.container?.running === true;
	}

	private async statusBody(): Promise<{ enabled: boolean; running: boolean }> {
		const state = await this.getState();
		return {
			enabled: this.env.JETSTREAM_ENABLED === "true",
			running: this.platformRunning() || isUp(state.status),
		};
	}

	private async supervise(): Promise<void> {
		const enabled = this.env.JETSTREAM_ENABLED === "true";
		const { running } = await this.statusBody();
		if (!enabled) {
			if (running) {
				await this.stop();
			}
			return;
		}
		if (running) {
			this.renewActivityTimeout();
			return;
		}
		try {
			await this.start(
				{
					envVars: containerEnv(this.env),
					entrypoint: ENTRYPOINT,
					enableInternet: true,
				},
				{
					portToCheck: PORT_TO_CHECK,
					retries: Math.ceil(START_WINDOW_MS / POLL_MS),
					waitInterval: POLL_MS,
				},
			);
		} catch (error) {
			console.error("jetstream start failed", error);
		}
	}
}

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		const url = new URL(request.url);
		if (request.method !== "GET" || url.pathname !== "/status") {
			return new Response("Not found", { status: 404 });
		}
		const container = env.JETSTREAM_CONTAINER.getByName("jetstream");
		return container.fetch(new Request("https://jetstream.internal/status"));
	},

	async scheduled(_controller: ScheduledController, env: Env): Promise<void> {
		const container = env.JETSTREAM_CONTAINER.getByName("jetstream");
		await container.fetch(
			new Request("https://jetstream.internal/supervise", {
				method: "POST",
				headers: { [SUPERVISE_HEADER]: "1" },
			}),
		);
	},
} satisfies ExportedHandler<Env>;
