import { supabaseEnv } from "@/lib/supabase/env";
import { createBrowserClient } from "@supabase/ssr";

/**
 * Supabase client for Client Components.
 *
 * `@supabase/ssr` stores the session in cookies rather than localStorage, so
 * the server side can read it too.
 */
export function createClient() {
	const { url, key } = supabaseEnv();

	return createBrowserClient(url, key);
}
