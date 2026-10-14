import SignOutButton from "@/components/SignOutButton";
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

	return (
		<div className="flex min-h-screen flex-col">
			<header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-3">
				<span className="text-sm font-medium text-zinc-900">
					Lab Data Integrations
				</span>
				<div className="flex items-center gap-4">
					<span className="text-sm text-zinc-500">{user.email}</span>
					<SignOutButton />
				</div>
			</header>

			{children}
		</div>
	);
}
