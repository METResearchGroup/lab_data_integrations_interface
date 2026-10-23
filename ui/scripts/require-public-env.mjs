const required = [
	"NEXT_PUBLIC_API_URL",
	"NEXT_PUBLIC_SUPABASE_URL",
	"NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
];

const missing = required.filter((name) => !process.env[name]);
if (missing.length > 0) {
	console.error(
		`Set these before building the UI. Values are inlined into the client bundle: ${missing.join(", ")}`,
	);
	process.exit(1);
}

if (process.env.NEXT_PUBLIC_API_URL.endsWith("/")) {
	console.error("NEXT_PUBLIC_API_URL must not have a trailing slash.");
	process.exit(1);
}
