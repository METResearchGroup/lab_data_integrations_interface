import { createClient } from "@/lib/supabase/client";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function errorMessage(response: Response): Promise<string> {
	try {
		const body = await response.json();
		if (typeof body?.detail === "string") return body.detail;
	} catch {
		// Not JSON — fall through to the status line.
	}
	return `Request failed (${response.status}).`;
}

/**
 * Hands a natural-language query to the backend.
 *
 * The backend acknowledges with 202 and mails the results when the query
 * finishes, so there is nothing to return and nothing to poll.
 */
export async function submitQuery(query: string): Promise<void> {
	const supabase = createClient();
	const {
		data: { session },
	} = await supabase.auth.getSession();

	if (!session) {
		throw new Error("Your session has expired. Sign in again to run queries.");
	}

	const response = await fetch(`${BASE_URL}/query`, {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
			// backend/auth.py reads the email to mail results to off this token.
			Authorization: `Bearer ${session.access_token}`,
		},
		// The endpoint declares Body(..., embed=False), so the body is the bare
		// string — `{"query": ...}` would be rejected as unprocessable.
		body: JSON.stringify(query),
	});

	if (!response.ok) throw new Error(await errorMessage(response));
}
