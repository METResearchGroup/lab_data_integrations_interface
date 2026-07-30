"use client";

import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import { useState } from "react";

interface LoginFormProps {
	/** Path to land on after a successful sign-in. Already validated server-side. */
	next: string;
}

export default function LoginForm({ next }: LoginFormProps) {
	const router = useRouter();
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [error, setError] = useState<string>();
	const [isSubmitting, setIsSubmitting] = useState(false);

	async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (isSubmitting) return;

		setError(undefined);
		setIsSubmitting(true);

		const supabase = createClient();
		const { error: signInError } = await supabase.auth.signInWithPassword({
			email,
			password,
		});

		if (signInError) {
			setError(signInError.message);
			setIsSubmitting(false);
			return;
		}

		// Stay disabled while navigating — the session cookie is set, and
		// refresh() re-runs the Server Components with the signed-in state.
		router.push(next);
		router.refresh();
	}

	return (
		<form onSubmit={handleSubmit} className="flex flex-col gap-4">
			<div className="flex flex-col gap-2">
				<label className="text-sm font-medium text-zinc-700" htmlFor="email">
					Email
				</label>
				<input
					id="email"
					type="email"
					value={email}
					onChange={(e) => setEmail(e.target.value)}
					required
					autoComplete="email"
					disabled={isSubmitting}
					className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 disabled:cursor-not-allowed disabled:opacity-50"
				/>
			</div>

			<div className="flex flex-col gap-2">
				<label className="text-sm font-medium text-zinc-700" htmlFor="password">
					Password
				</label>
				<input
					id="password"
					type="password"
					value={password}
					onChange={(e) => setPassword(e.target.value)}
					required
					autoComplete="current-password"
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
				{isSubmitting ? "Signing in..." : "Sign in"}
			</button>
		</form>
	);
}
