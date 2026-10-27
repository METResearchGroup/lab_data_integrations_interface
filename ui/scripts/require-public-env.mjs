import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SUPABASE_SECRET_ID = "lab-data-integrations-supabase-public";
const SUPABASE_SECRET_REGION = "us-east-2";
const SUPABASE_FIELDS = [
	"NEXT_PUBLIC_SUPABASE_URL",
	"NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
];

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../..");

const pythonSnippet = `
import json, sys
import boto3
from botocore.exceptions import ClientError

secret_id, region = sys.argv[1], sys.argv[2]
wanted = ["NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"]
client = boto3.client("secretsmanager", region_name=region)
try:
    response = client.get_secret_value(SecretId=secret_id)
except ClientError as exc:
    code = exc.response.get("Error", {}).get("Code", "unknown")
    print(code, file=sys.stderr)
    sys.exit(2)
try:
    data = json.loads(response.get("SecretString") or "")
except json.JSONDecodeError:
    print("not_json", file=sys.stderr)
    sys.exit(3)
if not isinstance(data, dict):
    print("not_object", file=sys.stderr)
    sys.exit(3)
missing = [name for name in wanted if not isinstance(data.get(name), str) or not data[name]]
if missing:
    print("missing_fields", file=sys.stderr)
    sys.exit(4)
json.dump({name: data[name] for name in wanted}, sys.stdout)
`;

function fail(message) {
	console.error(message);
	process.exit(1);
}

function pythonBinary() {
	const candidates = [];
	if (process.env.PYTHON) candidates.push(process.env.PYTHON);
	const venvPython = resolve(repoRoot, ".venv/bin/python");
	if (existsSync(venvPython)) candidates.push(venvPython);
	candidates.push("python3");
	for (const bin of candidates) {
		const probe = spawnSync(bin, ["-c", "import boto3"], { stdio: "ignore" });
		if (probe.status === 0) return bin;
	}
	return null;
}

function loadSupabasePublic() {
	const present = SUPABASE_FIELDS.filter((name) => process.env[name]);
	if (present.length === SUPABASE_FIELDS.length) return;
	if (present.length > 0) {
		fail(
			`Set both ${SUPABASE_FIELDS.join(" and ")} in the environment, or neither. When neither is set, the deploy reads both from Secrets Manager ${SUPABASE_SECRET_ID} (${SUPABASE_SECRET_REGION}).`,
		);
	}

	const python = pythonBinary();
	if (!python) {
		fail(
			`Could not import boto3. Set ${SUPABASE_FIELDS.join(" and ")}, or run with a Python that has boto3 so the deploy can read Secrets Manager ${SUPABASE_SECRET_ID}.`,
		);
	}

	const result = spawnSync(
		python,
		["-c", pythonSnippet, SUPABASE_SECRET_ID, SUPABASE_SECRET_REGION],
		{
			encoding: "utf8",
			stdio: ["ignore", "pipe", "pipe"],
		},
	);
	if (result.status !== 0) {
		const code = (result.stderr || "").trim().split("\n").at(-1) || "unknown";
		if (code === "ResourceNotFoundException") {
			fail(
				`Secrets Manager secret ${SUPABASE_SECRET_ID} does not exist in ${SUPABASE_SECRET_REGION} yet. Create it with JSON fields ${SUPABASE_FIELDS.join(" and ")}, or export both before deploying.`,
			);
		}
		fail(
			`Could not read Secrets Manager secret ${SUPABASE_SECRET_ID} in ${SUPABASE_SECRET_REGION} (${code}). No values were printed.`,
		);
	}

	let parsed;
	try {
		parsed = JSON.parse(result.stdout);
	} catch {
		fail(
			`Secrets Manager secret ${SUPABASE_SECRET_ID} did not return the two public fields.`,
		);
	}
	for (const name of SUPABASE_FIELDS) {
		const value = parsed[name];
		if (typeof value !== "string" || value.length === 0) {
			fail(`Secrets Manager secret ${SUPABASE_SECRET_ID} is missing ${name}.`);
		}
		process.env[name] = value;
	}
	console.log(
		`Loaded ${SUPABASE_FIELDS.join(" and ")} from Secrets Manager ${SUPABASE_SECRET_ID}. Values were not printed.`,
	);
}

function execDeploy(argv) {
	const index = argv.indexOf("--exec");
	if (index === -1) return;
	const command = argv.slice(index + 1);
	if (command.length === 0) {
		fail("--exec needs the deploy command.");
	}
	// The Worker config reads these names while vinext-cloudflare deploy is
	// running. A separate shell command after this process would not see them.
	const result = spawnSync(command[0], command.slice(1), {
		stdio: "inherit",
		env: process.env,
	});
	process.exit(result.status === null ? 1 : result.status);
}

if (!process.env.NEXT_PUBLIC_API_URL) {
	fail(
		"Set NEXT_PUBLIC_API_URL before building the UI. The value is inlined into the client bundle.",
	);
}

loadSupabasePublic();

function assertSupabaseHost() {
	let host = "";
	try {
		host = new URL(process.env.NEXT_PUBLIC_SUPABASE_URL).hostname;
	} catch {
		fail(
			"NEXT_PUBLIC_SUPABASE_URL is not an absolute URL. The value was not printed.",
		);
	}
	if (!host.endsWith(".supabase.co")) {
		fail(
			"NEXT_PUBLIC_SUPABASE_URL must be a supabase.co project host. The value was not printed.",
		);
	}
}

assertSupabaseHost();

if (process.env.NEXT_PUBLIC_API_URL.endsWith("/")) {
	fail("NEXT_PUBLIC_API_URL must not have a trailing slash.");
}

execDeploy(process.argv.slice(2));
