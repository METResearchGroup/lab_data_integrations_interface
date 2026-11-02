import LoginForm from "@/components/LoginForm";
import { createClient } from "@/lib/supabase/server";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
	title: "Sign in",
};

/**
 * Constrain the post-login destination to a path on this site.
 *
 * `next` comes from the query string, so without this an attacker could send
 * someone a link like `/login?next=https://evil.example` and have the app
 * redirect there after a successful sign-in. Protocol-relative URLs (`//host`)
 * are rejected for the same reason.
 */
function safeNext(next: string | string[] | undefined): string {
	if (typeof next !== "string") return "/";
	if (!next.startsWith("/") || next.startsWith("//")) return "/";
	return next;
}

// Set by /auth/confirm.
const LINK_ERRORS: Record<string, string> = {
	invalid_link: "That email link is invalid.",
	expired_link: "That email link has expired or was already used.",
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
