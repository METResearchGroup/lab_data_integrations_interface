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
