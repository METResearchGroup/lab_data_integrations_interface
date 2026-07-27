import LoginForm from "@/components/LoginForm";
import { createClient } from "@/lib/supabase/server";
import type { Metadata } from "next";
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

export default async function LoginPage({
	searchParams,
}: {
	searchParams: Promise<{ next?: string | string[] }>;
}) {
	const destination = safeNext((await searchParams).next);

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
					<p className="text-sm text-zinc-500">
						Use the account you were given for the lab data tool.
					</p>
				</div>

				<LoginForm next={destination} />
			</div>
		</main>
	);
}
