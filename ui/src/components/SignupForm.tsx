"use client";

import { ALLOWED_EMAIL_DOMAIN } from "@/lib/constants";
import { createClient } from "@/lib/supabase/client";
import { validateSignupEmail } from "@/lib/validation";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

const INPUT_CLASS =
	"w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 disabled:cursor-not-allowed disabled:opacity-50";

const BUTTON_CLASS =
	"w-full rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50";

export default function SignupForm() {
	const router = useRouter();
	const [step, setStep] = useState<"details" | "verify">("details");
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [confirmation, setConfirmation] = useState("");
	const [code, setCode] = useState("");
	const [error, setError] = useState<string>();
	const [notice, setNotice] = useState<string>();
	const [accountExists, setAccountExists] = useState(false);
	const [isSubmitting, setIsSubmitting] = useState(false);

	async function handleSignup(event: React.FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (isSubmitting) return;

		const emailError = validateSignupEmail(email);
		if (emailError) {
			setError(emailError);
			return;
		}
		if (password !== confirmation) {
			setError("Passwords do not match.");
			return;
		}

		setError(undefined);
		setAccountExists(false);
		setIsSubmitting(true);

		const supabase = createClient();
		const { data, error: signUpError } = await supabase.auth.signUp({
			email: email.trim(),
			password,
		});

		if (signUpError) {
			setError(signUpError.message);
			setIsSubmitting(false);
			return;
		}

		// "Confirm email" off in Supabase: already signed in.
		if (data.session) {
			router.push("/");
			router.refresh();
			return;
		}

		// Supabase returns a user with no identities for an existing email.
		if (data.user?.identities?.length === 0) {
			setAccountExists(true);
			setIsSubmitting(false);
			return;
		}

		setStep("verify");
		setIsSubmitting(false);
	}

	async function handleVerify(event: React.FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (isSubmitting) return;

		setError(undefined);
		setNotice(undefined);
		setIsSubmitting(true);

		const supabase = createClient();
		const { error: verifyError } = await supabase.auth.verifyOtp({
			email: email.trim(),
			token: code.trim(),
			type: "email",
		});

		if (verifyError) {
			setError(verifyError.message);
			setIsSubmitting(false);
			return;
		}

		router.push("/");
		router.refresh();
	}

	async function handleResend() {
		if (isSubmitting) return;

		setError(undefined);
		setNotice(undefined);
		setIsSubmitting(true);

		const supabase = createClient();
		const { error: resendError } = await supabase.auth.resend({
			type: "signup",
			email: email.trim(),
		});

		if (resendError) {
			setError(resendError.message);
		} else {
			setNotice("Sent a new code.");
		}
		setIsSubmitting(false);
	}

	if (step === "verify") {
		return (
			<form onSubmit={handleVerify} className="flex flex-col gap-4">
				<p className="text-sm text-zinc-600">
					We emailed a verification code to{" "}
					<span className="font-medium text-zinc-900">{email.trim()}</span>.
				</p>

				<div className="flex flex-col gap-2">
					<label className="text-sm font-medium text-zinc-700" htmlFor="code">
						Verification code
					</label>
					<input
						id="code"
						type="text"
						inputMode="numeric"
						autoComplete="one-time-code"
						value={code}
						onChange={(e) => setCode(e.target.value)}
						required
						disabled={isSubmitting}
						className={INPUT_CLASS}
					/>
				</div>

				{error && <p className="text-sm text-red-600">{error}</p>}
				{notice && <p className="text-sm text-zinc-600">{notice}</p>}

				<button type="submit" disabled={isSubmitting} className={BUTTON_CLASS}>
					{isSubmitting ? "Verifying..." : "Verify"}
				</button>

				<button
					type="button"
					onClick={handleResend}
					disabled={isSubmitting}
					className="text-sm text-zinc-500 hover:text-zinc-900 disabled:cursor-not-allowed disabled:opacity-50"
				>
					Resend code
				</button>
			</form>
		);
	}

	return (
		<form onSubmit={handleSignup} className="flex flex-col gap-4">
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
					placeholder={`you@${ALLOWED_EMAIL_DOMAIN}`}
					disabled={isSubmitting}
					className={INPUT_CLASS}
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
					autoComplete="new-password"
					disabled={isSubmitting}
					className={INPUT_CLASS}
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
					className={INPUT_CLASS}
				/>
			</div>

			{error && <p className="text-sm text-red-600">{error}</p>}
			{accountExists && (
				<p className="text-sm text-red-600">
					An account with this email already exists.{" "}
					<Link href="/login" className="underline">
						Sign in
					</Link>{" "}
					instead.
				</p>
			)}

			<button type="submit" disabled={isSubmitting} className={BUTTON_CLASS}>
				{isSubmitting ? "Creating account..." : "Create account"}
			</button>
		</form>
	);
}
