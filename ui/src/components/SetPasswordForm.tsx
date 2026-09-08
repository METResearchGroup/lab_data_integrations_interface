"use client";

import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function SetPasswordForm() {
	const router = useRouter();
	const [password, setPassword] = useState("");
	const [confirmation, setConfirmation] = useState("");
	const [error, setError] = useState<string>();
	const [isSubmitting, setIsSubmitting] = useState(false);

	async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (isSubmitting) return;

		if (password !== confirmation) {
			setError("Passwords do not match.");
			return;
		}

		setError(undefined);
		setIsSubmitting(true);

		const supabase = createClient();
		const { error: updateError } = await supabase.auth.updateUser({ password });

		if (updateError) {
			setError(updateError.message);
			setIsSubmitting(false);
			return;
		}

		router.push("/");
		router.refresh();
	}

	return (
		<form onSubmit={handleSubmit} className="flex flex-col gap-4">
			<div className="flex flex-col gap-2">
				<label className="text-sm font-medium text-zinc-700" htmlFor="password">
					New password
				</label>
				<input
					id="password"
					type="password"
					value={password}
					onChange={(e) => setPassword(e.target.value)}
					required
					autoComplete="new-password"
					disabled={isSubmitting}
					className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 disabled:cursor-not-allowed disabled:opacity-50"
				/>
			</div>

			<div className="flex flex-col gap-2">
				<label
					className="text-sm font-medium text-zinc-700"
					htmlFor="confirmation"
				>
					Confirm password
				</label>
				<input
					id="confirmation"
					type="password"
					value={confirmation}
					onChange={(e) => setConfirmation(e.target.value)}
					required
					autoComplete="new-password"
					disabled={isSubmitting}
					className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 disabled:cursor-not-allowed disabled:opacity-50"
				/>
			</div>

			{error && <p className="text-sm text-red-600">{error}</p>}

			<button
				type="submit"
				disabled={isSubmitting}
				className="w-full rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
			>
				{isSubmitting ? "Saving..." : "Save password"}
			</button>
		</form>
	);
}
