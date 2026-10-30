import { createClient } from "@/lib/supabase/server";
import { safeNext } from "@/lib/validation";
import { type NextRequest, NextResponse } from "next/server";

/**
 * Finishes Microsoft sign-in: trades the PKCE code Supabase sends back for a
 * session cookie.
 */
export async function GET(request: NextRequest) {
	const { searchParams } = request.nextUrl;
	const code = searchParams.get("code");
	const next = safeNext(searchParams.get("next") ?? undefined);

	// No code when the user cancels at Microsoft or the signup hook rejects them.
	if (!code) {
		return NextResponse.redirect(
			new URL("/login?error=oauth_failed", request.url),
		);
	}

	const supabase = await createClient();
	const { error } = await supabase.auth.exchangeCodeForSession(code);

	if (error) {
		return NextResponse.redirect(
			new URL("/login?error=oauth_failed", request.url),
		);
	}

	return NextResponse.redirect(new URL(next, request.url));
}
