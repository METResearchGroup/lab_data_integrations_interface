import LoginForm from "@/components/LoginForm";
import MicrosoftSignInButton from "@/components/MicrosoftSignInButton";
import { createClient } from "@/lib/supabase/server";
import { safeNext } from "@/lib/validation";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
	title: "Sign in",
};

// Set by /auth/confirm and /auth/callback.
const LINK_ERRORS: Record<string, string> = {
	invalid_link: "That email link is invalid.",
	expired_link: "That email link has expired or was already used.",
	oauth_failed:
		"Microsoft sign-in failed. It needs a Northwestern Microsoft account.",
};

export default async function LoginPage({
	searchParams,
}: {
	searchParams: Promise<{
		next?: string | string[];
		error?: string | string[];
	}>;
}) {
	const params = await searchParams;
	const destination = safeNext(params.next);
	const linkError =
		typeof params.error === "string" ? LINK_ERRORS[params.error] : undefined;

	const supabase = await createClient();
	const {
		data: { user },
	} = await supabase.auth.getUser();

	if (user) redirect(destination);

	return (
		<main className="flex min-h-screen flex-col items-center justify-center bg-zinc-50">
			<div className="w-full max-w-sm rounded-xl bg-white p-8 shadow-sm flex flex-col gap-6">
				<div className="flex flex-col gap-1">
					<h1 className="text-lg font-medium text-zinc-900">Sign in</h1>
					<p className="text-sm text-zinc-500">Sign in to the lab data tool.</p>
				</div>

				{linkError && <p className="text-sm text-red-600">{linkError}</p>}

				<MicrosoftSignInButton next={destination} />

				<LoginForm next={destination} />

				<p className="text-center text-sm text-zinc-500">
					Don&apos;t have an account?{" "}
					<Link href="/signup" className="font-medium text-zinc-900 underline">
						Sign up
					</Link>
				</p>
			</div>
		</main>
	);
}
