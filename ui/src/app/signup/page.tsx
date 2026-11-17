import MicrosoftSignInButton from "@/components/MicrosoftSignInButton";
import SignupForm from "@/components/SignupForm";
import { createClient } from "@/lib/supabase/server";
import { formatAllowedDomains } from "@/lib/validation";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
	title: "Create account",
};

export default async function SignupPage() {
	const supabase = await createClient();
	const {
		data: { user },
	} = await supabase.auth.getUser();

	if (user) redirect("/");

	return (
		<main className="flex min-h-screen flex-col items-center justify-center bg-zinc-50">
			<div className="w-full max-w-sm rounded-xl bg-white p-8 shadow-sm flex flex-col gap-6">
				<div className="flex flex-col gap-1">
					<h1 className="text-lg font-medium text-zinc-900">Create account</h1>
					<p className="text-sm text-zinc-500">
						Requires a {formatAllowedDomains()} email.
					</p>
				</div>

				<MicrosoftSignInButton next="/" />

				<SignupForm />

				<p className="text-center text-sm text-zinc-500">
					Already have an account?{" "}
					<Link href="/login" className="font-medium text-zinc-900 underline">
						Sign in
					</Link>
				</p>
			</div>
		</main>
	);
}
