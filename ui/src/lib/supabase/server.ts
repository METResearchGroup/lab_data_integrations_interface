import { supabaseEnv } from "@/lib/supabase/env";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/**
 * Supabase client for Server Components, route handlers and server actions.
 *
 * Create a new client per request — never share one across requests.
 */
export async function createClient() {
	const { url, key } = supabaseEnv();
	const cookieStore = await cookies();

	return createServerClient(url, key, {
		cookies: {
			getAll: () => cookieStore.getAll(),
			setAll: (cookiesToSet) => {
				try {
					for (const { name, value, options } of cookiesToSet) {
						cookieStore.set(name, value, options);
					}
				} catch {
					// Called from a Server Component render, where cookies are
					// read-only. proxy.ts performs the session refresh instead.
				}
			},
		},
	});
}
