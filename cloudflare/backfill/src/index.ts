import { Container } from "@cloudflare/containers";

// The image's CMD is uvicorn. This container replaces it at start.
const ENTRYPOINT = [
	"/app/.venv/bin/python",
	"-m",
	"bluesky_backfill_app.fetch_repos.main",
];

const FORWARDED = [
	"AWS_ACCESS_KEY_ID",
	"AWS_SECRET_ACCESS_KEY",
	"AWS_SESSION_TOKEN",
	"OTEL_EXPORTER_OTLP_HEADERS",
] as const;

// Same start window as Jetstream. The fetch worker does not bind a port.
// start() still returns once the instance is running and the runtime reports
// that nothing is listening. See @cloudflare/containers.
const START_WINDOW_MS = 240_000;
const POLL_MS = 3_000;
const PORT_TO_CHECK = 8000;

// Latest POST /start arms this long a run. The SQS loop does not extend it.
const RUN_WINDOW_SECONDS = 6 * 60 * 60;
const RUN_WINDOW_MS = RUN_WINDOW_SECONDS * 1000;
const DEADLINE_KEY = "backfillDeadlineMs";

const CONTROL_HEADER = "x-ldi-backfill-control";

export interface Env {
	BACKFILL_CONTAINER: DurableObjectNamespace<BackfillContainer>;
	BACKFILL_TRIGGER_TOKEN?: string;
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

export async function bearerMatches(
	request: Request,
	expected: string | undefined,
): Promise<boolean> {
	if (typeof expected !== "string" || expected.length === 0) {
		return false;
	}
	const header = request.headers.get("Authorization") ?? "";
	const prefix = "Bearer ";
	if (!header.startsWith(prefix)) {
		return false;
	}
	const token = header.slice(prefix.length);
	const encoder = new TextEncoder();
	const presented = encoder.encode(token);
	const stored = encoder.encode(expected);
	if (presented.byteLength !== stored.byteLength) {
		return false;
	}
	return crypto.subtle.timingSafeEqual(presented, stored);
}

/**
 * On-demand backfill. Nothing starts the process until POST /start.
 *
 * sleepAfter is 6h, so a stable Durable Object stops the process then.
 * A schedule stored at start time also calls stop(), which still fires if
 * the object restarts and refreshes its in-memory timer. POST /start while
 * the process is up moves that deadline out by another 6 hours. The SQS
 * loop does not. setInactivityTimeout is the same 6 hours, because
 * Cloudflare stops a container shortly after its Durable Object goes idle
 * when that timeout is unset. The constructor sets the remaining time again
 * if the object restarts while the process is up. SIGTERM hits the handler
 * in fetch_repos/main.py, which flushes a partial buffer before it exits.
 */
export class BackfillContainer extends Container<Env> {
	sleepAfter = "6h";
	enableInternet = true;
	entrypoint = ENTRYPOINT;

	constructor(ctx: DurableObjectState<{}>, env: Env) {
		super(ctx, env);
		void ctx.blockConcurrencyWhile(() => this.restoreKeepAlive());
	}

	private async restoreKeepAlive(): Promise<void> {
		const container = this.ctx.container;
		if (!container?.running) {
			return;
		}
		const deadline = await this.ctx.storage.get<number>(DEADLINE_KEY);
		const remaining = typeof deadline === "number" ? deadline - Date.now() : 0;
		if (remaining <= 0) {
			await this.stop();
			return;
		}
		await container.setInactivityTimeout(Math.min(remaining, RUN_WINDOW_MS));
	}

	override async fetch(request: Request): Promise<Response> {
		const url = new URL(request.url);
		if (request.method === "GET" && url.pathname === "/status") {
			return Response.json({ running: await this.running() });
		}
		if (request.headers.get(CONTROL_HEADER) !== "1") {
			return new Response("Not found", { status: 404 });
		}
		if (request.method === "POST" && url.pathname === "/start") {
			return this.begin();
		}
		if (request.method === "POST" && url.pathname === "/stop") {
			return this.end();
		}
		return new Response("Not found", { status: 404 });
	}

	// Fired by this.schedule() 6 hours after the latest /start.
	async stopIfDue(): Promise<void> {
		const deadline = await this.ctx.storage.get<number>(DEADLINE_KEY);
		if (typeof deadline !== "number" || Date.now() + 15_000 < deadline) {
			return;
		}
		await this.stop();
		await this.ctx.storage.delete(DEADLINE_KEY);
	}

	private platformRunning(): boolean {
		const runtime = this as unknown as { container?: { running?: boolean } };
		return runtime.container?.running === true;
	}

	private async running(): Promise<boolean> {
		const state = await this.getState();
		return this.platformRunning() || isUp(state.status);
	}

	private async launch(): Promise<void> {
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
	}

	private async armWindow(): Promise<void> {
		const deadline = Date.now() + RUN_WINDOW_MS;
		await this.ctx.storage.put(DEADLINE_KEY, deadline);
		this.renewActivityTimeout();
		const container = this.ctx.container;
		if (container?.running) {
			await container.setInactivityTimeout(RUN_WINDOW_MS);
		}
		await this.schedule(RUN_WINDOW_SECONDS, "stopIfDue");
	}

	private async begin(): Promise<Response> {
		try {
			await this.launch();
		} catch (error) {
			console.error("backfill start failed", error);
			if (!(await this.running())) {
				return Response.json({ detail: "container start failed" }, { status: 500 });
			}
		}
		await this.armWindow();
		return Response.json({ running: true });
	}

	private async end(): Promise<Response> {
		await this.stop();
		await this.ctx.storage.delete(DEADLINE_KEY);
		return Response.json({ running: false });
	}
}

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		const url = new URL(request.url);
		const container = env.BACKFILL_CONTAINER.getByName("backfill");
		if (request.method === "GET" && url.pathname === "/status") {
			return container.fetch(new Request("https://backfill.internal/status"));
		}
		if (
			request.method === "POST" &&
			(url.pathname === "/start" || url.pathname === "/stop")
		) {
			if (!(await bearerMatches(request, env.BACKFILL_TRIGGER_TOKEN))) {
				return Response.json({ detail: "Unauthorized" }, { status: 401 });
			}
			return container.fetch(
				new Request(`https://backfill.internal${url.pathname}`, {
					method: "POST",
					headers: { [CONTROL_HEADER]: "1" },
				}),
			);
		}
		return new Response("Not found", { status: 404 });
	},
} satisfies ExportedHandler<Env>;
