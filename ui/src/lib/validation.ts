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
