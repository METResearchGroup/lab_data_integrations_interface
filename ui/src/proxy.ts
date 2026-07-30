import { supabaseEnv } from "@/lib/supabase/env";
import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

/**
 * Runs before every matched request (Next.js 16 renamed Middleware to Proxy).
 *
 * Two jobs:
 *
 * 1. Refresh the Supabase session. Server Components cannot write cookies, so
 *    without this the access token would expire mid-session and users would be
 *    silently logged out.
 * 2. Send signed-out visitors to /login before the page renders.
 *
 * The redirect here is an *optimistic* check — Next's docs are explicit that
 * proxy "should not be used as a full session management or authorization
 * solution". The authoritative check lives in app/(protected)/layout.tsx.
 */
export async function proxy(request: NextRequest) {
	// Reassigned in setAll: NextResponse.next() snapshots the request headers,
	// so refreshed cookies only reach this request's render if it is rebuilt.
	let response = NextResponse.next({ request });

	const { url, key } = supabaseEnv();

	const supabase = createServerClient(url, key, {
		cookies: {
			getAll: () => request.cookies.getAll(),
			setAll: (cookiesToSet, headers) => {
				for (const { name, value } of cookiesToSet) {
					request.cookies.set(name, value);
				}

				response = NextResponse.next({ request });

				for (const { name, value, options } of cookiesToSet) {
					response.cookies.set(name, value, options);
				}

				// Cache-Control/Expires/Pragma from @supabase/ssr. Without these a
				// CDN could cache one user's session cookie and serve it to another.
				for (const [header, headerValue] of Object.entries(headers)) {
					response.headers.set(header, headerValue);
				}
			},
		},
	});

	// Triggers the refresh. Do not remove, and do not swap for getSession(),
	// which trusts the cookie contents without verifying them.
	const {
		data: { user },
	} = await supabase.auth.getUser();

	if (!user && !request.nextUrl.pathname.startsWith("/login")) {
		const loginUrl = new URL("/login", request.url);

		// Remember the destination so sign-in returns the user to it. Skipped for
		// "/" since that is where login lands by default.
		const destination = request.nextUrl.pathname + request.nextUrl.search;
		if (destination !== "/") {
			loginUrl.searchParams.set("next", destination);
		}

		return NextResponse.redirect(loginUrl);
	}

	return response;
}

export const config = {
	matcher: [
		/*
		 * Every path except static assets, which never need an auth check:
		 * _next/static, _next/image, favicon.ico and common image extensions.
		 */
		"/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
	],
};
