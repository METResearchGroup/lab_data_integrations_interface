import SetPasswordForm from "@/components/SetPasswordForm";
import { createClient } from "@/lib/supabase/server";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
	title: "Set your password",
};

export default async function SetPasswordPage() {
	const supabase = await createClient();
	const {
		data: { user },
	} = await supabase.auth.getUser();

	if (!user) redirect("/login");

	return (
		<main className="flex min-h-screen flex-col items-center justify-center bg-zinc-50">
			<div className="w-full max-w-sm rounded-xl bg-white p-8 shadow-sm flex flex-col gap-6">
				<div className="flex flex-col gap-1">
					<h1 className="text-lg font-medium text-zinc-900">
						Set your password
					</h1>
					<p className="text-sm text-zinc-500">
						Choose a password for {user.email}. You will use it to sign in from
						now on.
					</p>
				</div>

				<SetPasswordForm />
			</div>
		</main>
	);
}
