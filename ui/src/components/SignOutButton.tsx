"use client";

import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function SignOutButton() {
	const router = useRouter();
	const [isSigningOut, setIsSigningOut] = useState(false);

	async function handleSignOut() {
		if (isSigningOut) return;
		setIsSigningOut(true);

		const supabase = createClient();
		await supabase.auth.signOut();

		// refresh() re-runs the Server Components, which now see no session.
		router.push("/login");
		router.refresh();
	}

	return (
		<button
			type="button"
			onClick={handleSignOut}
			disabled={isSigningOut}
			className="text-sm font-medium text-zinc-500 hover:text-zinc-900 disabled:cursor-not-allowed disabled:opacity-50"
		>
			{isSigningOut ? "Signing out..." : "Sign out"}
		</button>
	);
}
