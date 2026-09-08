import { supabaseEnv } from "@/lib/supabase/env";
import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/auth/confirm"];

/**
 * Refreshes the Supabase session and redirects signed-out visitors to /login.
 */
export async function proxy(request: NextRequest) {
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

				for (const [header, headerValue] of Object.entries(headers)) {
					response.headers.set(header, headerValue);
				}
			},
		},
	});

	const {
		data: { user },
	} = await supabase.auth.getUser();

	const isPublic = PUBLIC_PATHS.some((path) =>
		request.nextUrl.pathname.startsWith(path),
	);

	if (!user && !isPublic) {
		const loginUrl = new URL("/login", request.url);

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
		"/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
	],
};
