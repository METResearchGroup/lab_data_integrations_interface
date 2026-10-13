"use client";

import QueryForm from "@/components/QueryForm";
import QuerySentNotice from "@/components/QuerySentNotice";
import { submitQuery } from "@/lib/api";
import { DEMO_QUERIES } from "@/lib/constants";
import { useState } from "react";

interface QueryConsoleProps {
	email?: string;
	demo?: boolean;
}

export default function QueryConsole({ email, demo }: QueryConsoleProps) {
	const [isSending, setIsSending] = useState(false);
	const [sentQuery, setSentQuery] = useState<string>();
	const [error, setError] = useState<string>();
	// Bumped on each successful send: remounting QueryForm clears the textarea.
	const [sendCount, setSendCount] = useState(0);
	const [presetQuery, setPresetQuery] = useState("");

	async function handleSubmit(query: string) {
		setError(undefined);
		setSentQuery(undefined);
		setIsSending(true);
		try {
			await submitQuery(query);
			setSentQuery(query);
			setPresetQuery("");
			setSendCount((count) => count + 1);
		} catch (e) {
			setError(e instanceof Error ? e.message : "Something went wrong");
		} finally {
			setIsSending(false);
		}
	}

	return (
		<div className="flex flex-col gap-6">
			{demo && (
				<div className="flex flex-wrap gap-2">
					{DEMO_QUERIES.map(({ label, text }) => (
						<button
							key={label}
							type="button"
							onClick={() => setPresetQuery(text)}
							disabled={isSending}
							className="rounded-full border border-zinc-300 px-3 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50"
						>
							{label}
						</button>
					))}
				</div>
			)}

			<QueryForm
				key={`${sendCount}-${presetQuery}`}
				initialQuery={presetQuery}
				onSubmit={handleSubmit}
				disabled={isSending}
			/>

			{error && <p className="text-sm text-red-600">{error}</p>}

			{sentQuery && <QuerySentNotice query={sentQuery} email={email} />}
		</div>
	);
}
