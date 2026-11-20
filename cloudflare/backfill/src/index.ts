import { Container } from "@cloudflare/containers";

// The fetch worker does not listen. Start it with ctx.container.start().
// Container.start() from @cloudflare/containers probes a TCP port, and when
// the last error is "Network connection lost" it aborts the Durable Object.
const ENTRYPOINT = [
	"/app/.venv/bin/python",
	"-m",
	"bluesky_backfill_app.fetch_repos.main",
];

// The process reads the OTLP header from Secrets Manager when that name is
// absent (lib/aws/secrets_env.py). Forward AWS credentials for that read,
// plus deploy settings that are not secrets. BACKFILL_TRIGGER_TOKEN stays
// on the Worker and is not copied into the container.
const FORWARDED = [
	"AWS_ACCESS_KEY_ID",
	"AWS_SECRET_ACCESS_KEY",
	"AWS_SESSION_TOKEN",
	"OTEL_RESOURCE_ATTRIBUTES",
	"DEPLOYMENT_ENVIRONMENT",
] as const;

// Platform cap. Without this, Cloudflare stops the container shortly after the
// Durable Object goes idle. The minute cron sets it again.
const KEEPALIVE_MS = 6 * 60 * 60 * 1000;
// Set by POST /start. Cleared by POST /stop and by a drained queue.
const WANTED_KEY = "backfillWanted";

const CONTROL_HEADER = "x-ldi-backfill-control";

export interface Env {
	BACKFILL_CONTAINER: DurableObjectNamespace<BackfillContainer>;
	BACKFILL_TRIGGER_TOKEN?: string;
	AWS_ACCESS_KEY_ID?: string;
	AWS_SECRET_ACCESS_KEY?: string;
	AWS_SESSION_TOKEN?: string;
	OTEL_RESOURCE_ATTRIBUTES?: string;
	DEPLOYMENT_ENVIRONMENT?: string;
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

function errorText(error: unknown): string {
	const message = error instanceof Error ? error.message : String(error);
	return message.slice(0, 300);
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
 * A run has no time limit. It ends on POST /stop, or when the process exits 0
 * because the queue drained. While a run is wanted, the minute cron renews the
 * keep-alive and restarts a process that exited any other way. SIGTERM hits the
 * handler in fetch_repos/main.py, which flushes a partial buffer and exits 143.
 */
export class BackfillContainer extends Container<Env> {
	sleepAfter = "30m";
	enableInternet = true;
	entrypoint = ENTRYPOINT;

	private exitWatch: Promise<void> | undefined;

	constructor(ctx: DurableObjectState<{}>, env: Env) {
		super(ctx, env);
		void ctx.blockConcurrencyWhile(() => this.restoreKeepAlive());
	}

	private async restoreKeepAlive(): Promise<void> {
		const container = this.ctx.container;
		if (!container?.running) {
			return;
		}
		if (await this.ctx.storage.get<boolean>(WANTED_KEY)) {
			await container.setInactivityTimeout(KEEPALIVE_MS);
			this.watchExit();
		}
	}

	override async onActivityExpired(): Promise<void> {
		// Leave the process running. The base method calls stop().
		console.log("backfill activity timer elapsed; leaving the process running");
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
		if (request.method === "POST" && url.pathname === "/supervise") {
			await this.supervise();
			return new Response("ok");
		}
		return new Response("Not found", { status: 404 });
	}

	// A /start from before the cron stored this schedule. The library retries a
	// missing callback forever, so it has to exist for the row to be deleted.
	async stopIfDue(): Promise<void> {}

	private platformRunning(): boolean {
		const runtime = this as unknown as { container?: { running?: boolean } };
		return runtime.container?.running === true;
	}

	private async running(): Promise<boolean> {
		const state = await this.getState();
		return this.platformRunning() || isUp(state.status);
	}

	private launch(): void {
		const container = this.ctx.container;
		if (!container) {
			throw new Error("backfill container is not configured");
		}
		if (container.running) {
			return;
		}
		container.start({
			env: containerEnv(this.env),
			entrypoint: [...ENTRYPOINT],
			enableInternet: true,
		});
	}

	private async keepAlive(): Promise<void> {
		const container = this.ctx.container;
		if (!container?.running) {
			return;
		}
		await container.setInactivityTimeout(KEEPALIVE_MS);
		this.renewActivityTimeout();
	}

	// monitor() resolves on exit 0 and rejects on any other exit.
	private watchExit(): void {
		const container = this.ctx.container;
		if (this.exitWatch || !container?.running) {
			return;
		}
		const pending = container
			.monitor()
			.then(async () => {
				this.exitWatch = undefined;
				await this.ctx.storage.delete(WANTED_KEY);
				console.log("backfill queue drained; run finished");
			})
			.catch((error: unknown) => {
				this.exitWatch = undefined;
				const message = errorText(error);
				console.log("backfill container stopped", message);
				if (message.includes("Network connection lost") && this.ctx.container?.running) {
					console.log("backfill clearing a lost container connection");
					void this.ctx.container.destroy();
				}
			});
		this.exitWatch = pending;
		this.ctx.waitUntil(pending);
	}

	private async supervise(): Promise<void> {
		if (!(await this.ctx.storage.get<boolean>(WANTED_KEY))) {
			return;
		}
		try {
			this.launch();
		} catch (error) {
			console.error("backfill restart failed", errorText(error));
			return;
		}
		this.watchExit();
		await this.keepAlive();
	}

	private async begin(): Promise<Response> {
		try {
			this.launch();
		} catch (error) {
			console.error("backfill start failed", errorText(error));
			if (!(await this.running())) {
				return Response.json({ detail: "container start failed" }, { status: 500 });
			}
		}
		if (!(await this.running())) {
			console.error("backfill start returned before the container was running");
			return Response.json({ detail: "container start failed" }, { status: 500 });
		}
		await this.ctx.storage.put(WANTED_KEY, true);
		this.watchExit();
		await this.keepAlive();
		return Response.json({ running: true });
	}

	private async end(): Promise<Response> {
		// Clear first, so the cron cannot restart a process that is draining.
		await this.ctx.storage.delete(WANTED_KEY);
		await this.stop();
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

	async scheduled(_controller: ScheduledController, env: Env): Promise<void> {
		const container = env.BACKFILL_CONTAINER.getByName("backfill");
		await container.fetch(
			new Request("https://backfill.internal/supervise", {
				method: "POST",
				headers: { [CONTROL_HEADER]: "1" },
			}),
		);
	},
} satisfies ExportedHandler<Env>;
