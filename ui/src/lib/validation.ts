import { MIN_QUERY_LENGTH } from "@/lib/constants";

export function validateQuery(query: string): string | undefined {
	const trimmed = query.trim();
	if (trimmed.length === 0) return "Enter a query to run.";
	if (trimmed.length < MIN_QUERY_LENGTH) {
		return `Query must be at least ${MIN_QUERY_LENGTH} characters.`;
	}
	return undefined;
}
