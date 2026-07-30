/**
 * Supabase connection settings, read from the environment.
 *
 * Both vars must be referenced literally as `process.env.NEXT_PUBLIC_*` for
 * Next.js to inline them into the client bundle at build time — a dynamic
 * lookup such as `process.env[name]` would be left undefined in the browser.
 *
 * Resolved lazily so a missing var fails at first use with a clear message,
 * rather than at import time (which would break builds in environments that
 * don't need Supabase configured).
 */
export function supabaseEnv() {
	const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
	const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

	if (!url || !key) {
		throw new Error(
			"Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY. See ui/.env.local.example.",
		);
	}

	return { url, key };
}
