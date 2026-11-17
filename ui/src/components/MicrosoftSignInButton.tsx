"use client";

import { createClient } from "@/lib/supabase/client";
import { useState } from "react";

interface MicrosoftSignInButtonProps {
	/** Path to land on after sign-in. Already validated server-side. */
	next: string;
}

/**
 * Hidden until NEXT_PUBLIC_ENABLE_MICROSOFT_SIGN_IN=true, so the UI can merge
 * before the Azure provider is configured in Supabase.
 */
export default function MicrosoftSignInButton({
	next,
}: MicrosoftSignInButtonProps) {
	const [error, setError] = useState<string>();
	const [isRedirecting, setIsRedirecting] = useState(false);

	if (process.env.NEXT_PUBLIC_ENABLE_MICROSOFT_SIGN_IN !== "true") return null;

	async function handleClick() {
		if (isRedirecting) return;

		setError(undefined);
		setIsRedirecting(true);

		const callback = new URL("/auth/callback", window.location.origin);
		callback.searchParams.set("next", next);

		const supabase = createClient();
		const { error: oauthError } = await supabase.auth.signInWithOAuth({
			provider: "azure",
			options: { scopes: "email", redirectTo: callback.toString() },
		});

		// On success the browser is already navigating to Microsoft.
		if (oauthError) {
			setError(oauthError.message);
			setIsRedirecting(false);
		}
	}

	return (
		<div className="flex flex-col gap-4">
			<button
				type="button"
				onClick={handleClick}
				disabled={isRedirecting}
				className="w-full rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50"
			>
				{isRedirecting ? "Redirecting..." : "Continue with Microsoft"}
			</button>

			{error && <p className="text-sm text-red-600">{error}</p>}

			<div className="flex items-center gap-3 text-xs text-zinc-400">
				<div className="h-px flex-1 bg-zinc-200" />
				or
				<div className="h-px flex-1 bg-zinc-200" />
			</div>
		</div>
	);
}
