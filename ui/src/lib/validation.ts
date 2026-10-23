import { ALLOWED_EMAIL_DOMAINS, MIN_QUERY_LENGTH } from "@/lib/constants";

export function validateQuery(query: string): string | undefined {
	const trimmed = query.trim();
	if (trimmed.length === 0) return "Enter a query to run.";
	if (trimmed.length < MIN_QUERY_LENGTH) {
		return `Query must be at least ${MIN_QUERY_LENGTH} characters.`;
	}
	return undefined;
}

// UX only; the Supabase signup hook is the real gate.
export function validateSignupEmail(email: string): string | undefined {
	const normalized = email.trim().toLowerCase();
	if (!ALLOWED_EMAIL_DOMAINS.some((d) => normalized.endsWith(`@${d}`))) {
		return `Use your ${formatAllowedDomains()} email.`;
	}
	return undefined;
}

export function formatAllowedDomains(): string {
	return ALLOWED_EMAIL_DOMAINS.map((d) => `@${d}`).join(" or ");
}

/**
 * Constrain the post-login destination to a path on this site.
 *
 * `next` comes from the query string, so without this an attacker could send
 * someone a link like `/login?next=https://evil.example` and have the app
 * redirect there after a successful sign-in. Protocol-relative URLs (`//host`,
 * or `/\host`, which browsers read the same way) are rejected for the same
 * reason.
 */
export function safeNext(next: string | string[] | undefined): string {
	if (typeof next !== "string") return "/";
	if (!next.startsWith("/") || /^\/[/\\]/.test(next)) return "/";
	return next;
}
