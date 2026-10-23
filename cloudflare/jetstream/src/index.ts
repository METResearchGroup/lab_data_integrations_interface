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

// Platform cap. Without this, Cloudflare stops the container shortly after the
// Durable Object goes idle, which is what happened on the first boot. The
// minute cron and the constructor set it again, so a restart of the object
// does not clear the keep-alive.
const KEEPALIVE_MS = 6 * 60 * 60 * 1000;

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

function errorText(error: unknown): string {
	const message = error instanceof Error ? error.message : String(error);
	return message.slice(0, 300);
}

/**
 * One Jetstream writer for the preview account.
 *
 * getByName("jetstream") and max_instances 1 keep a single process, which is
 * what the DynamoDB cursor assumes. sleepAfter is 30m, and the default
 * onActivityExpired would SIGTERM the process then, because nothing proxies
 * HTTP at it to reset the timer. The override below does not stop it.
 * Cloudflare also stops a container shortly after its Durable Object goes
 * idle unless setInactivityTimeout is set. The cap is 6 hours, so the minute
 * cron sets it again, and the constructor sets it again when the object
 * restarts and the process is already up. The cron also restarts the process
 * if it has exited, and stops it when JETSTREAM_ENABLED is not "true".
 *
 * Container.start() from the library probes a TCP port. This process does
 * not listen. On the last probe, a "Network connection lost" error aborts
 * the Durable Object. The preview then has no instance, and the next start
 * fails with "no container instance" until the platform hands one out again.
 * supervise calls ctx.container.start() and does not probe a port.
 */
export class JetstreamContainer extends Container<Env> {
	sleepAfter = "30m";
	enableInternet = true;
	entrypoint = ENTRYPOINT;

	private exitWatch: Promise<void> | undefined;

	constructor(ctx: DurableObjectState<{}>, env: Env) {
		super(ctx, env);
		const container = ctx.container;
		if (container?.running) {
			void ctx.blockConcurrencyWhile(() => container.setInactivityTimeout(KEEPALIVE_MS));
			this.watchExit();
		}
	}

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

	private async statusBody(): Promise<{ enabled: boolean; running: boolean }> {
		return {
			enabled: this.env.JETSTREAM_ENABLED === "true",
			running: this.ctx.container?.running === true,
		};
	}

	private async keepAlive(): Promise<void> {
		const container = this.ctx.container;
		if (!container?.running) {
			return;
		}
		await container.setInactivityTimeout(KEEPALIVE_MS);
		this.renewActivityTimeout();
		console.log("jetstream inactivity timeout set", KEEPALIVE_MS);
	}

	private watchExit(): void {
		if (this.exitWatch) {
			return;
		}
		const container = this.ctx.container;
		if (!container?.running) {
			return;
		}
		const pending = container
			.monitor()
			.then(() => {
				this.exitWatch = undefined;
				console.log("jetstream container exited");
			})
			.catch((error: unknown) => {
				this.exitWatch = undefined;
				const message = errorText(error);
				console.log("jetstream container stopped", message);
				if (message.includes("Network connection lost") && this.ctx.container?.running) {
					console.log("jetstream clearing a lost container connection");
					void this.ctx.container.destroy();
				}
			});
		this.exitWatch = pending;
		this.ctx.waitUntil(pending);
	}

	private startContainer(): void {
		const container = this.ctx.container;
		if (!container) {
			throw new Error("jetstream container is not configured");
		}
		if (container.running) {
			return;
		}
		container.start({
			env: containerEnv(this.env),
			entrypoint: [...ENTRYPOINT],
			enableInternet: true,
		});
		console.log("jetstream container start requested");
	}

	private async supervise(): Promise<void> {
		const enabled = this.env.JETSTREAM_ENABLED === "true";
		const running = this.ctx.container?.running === true;
		if (!enabled) {
			if (running) {
				await this.stop();
			}
			return;
		}
		if (!running) {
			try {
				this.startContainer();
			} catch (error) {
				console.error("jetstream start failed", errorText(error));
				return;
			}
		}
		if (this.ctx.container?.running) {
			this.watchExit();
			await this.keepAlive();
			await this.logProcess();
		}
	}

	private async logProcess(): Promise<void> {
		const container = this.ctx.container;
		if (!container?.running) {
			return;
		}
		try {
			const process = await container.exec([
				"/app/.venv/bin/python",
				"-c",
				(
					"import pathlib\n"
					+ "cmd = pathlib.Path('/proc/1/cmdline').read_bytes().replace(bytes([0]), b' ').decode()\n"
					+ "status = pathlib.Path('/proc/1/status').read_text().splitlines()\n"
					+ "rss = next(line.split()[1] for line in status if line.startswith('VmRSS'))\n"
					+ "kind = 'writer' if 'bluesky_ingestion_jetstream' in cmd else 'other'\n"
					+ "print(kind, rss)\n"
				),
			]);
			const output = await process.output();
			const text = new TextDecoder().decode(output.stdout).trim();
			console.log("jetstream process", output.exitCode, text.slice(0, 80));
		} catch (error) {
			console.log("jetstream process check failed", errorText(error));
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
