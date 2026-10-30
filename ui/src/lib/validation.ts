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
// The domain is the exact text after the single "@", so a parent domain
// does not accept a lookalike or a different subdomain.
export function validateSignupEmail(email: string): string | undefined {
	const normalized = email.trim().toLowerCase();
	const at = normalized.indexOf("@");
	const domain = at >= 0 ? normalized.slice(at + 1) : "";
	const singleAt = at > 0 && at === normalized.lastIndexOf("@");
	if (!singleAt || !ALLOWED_EMAIL_DOMAINS.includes(domain)) {
		return `Use your ${formatAllowedDomains()} email.`;
	}
	return undefined;
}

export function formatAllowedDomains(): string {
	const labels = ALLOWED_EMAIL_DOMAINS.map((d) => `@${d}`);
	if (labels.length <= 1) return labels[0] ?? "";
	if (labels.length === 2) return `${labels[0]} or ${labels[1]}`;
	return `${labels.slice(0, -1).join(", ")}, or ${labels[labels.length - 1]}`;
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
