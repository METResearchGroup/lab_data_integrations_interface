import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

/**
 * Gate for every route in the (protected) group.
 *
 * proxy.ts already redirects signed-out visitors, but that check only looks at
 * the cookie. This one calls getUser(), which verifies the JWT with Supabase,
 * and is the authoritative check.
 */
export default async function ProtectedLayout({
	children,
}: {
	children: React.ReactNode;
}) {
	const supabase = await createClient();
	const {
		data: { user },
	} = await supabase.auth.getUser();

	if (!user) redirect("/login");

	return <>{children}</>;
}
