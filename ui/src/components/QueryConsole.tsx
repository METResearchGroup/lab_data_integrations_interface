"use client";

import QueryForm from "@/components/QueryForm";
import QuerySentNotice from "@/components/QuerySentNotice";
import { submitQuery } from "@/lib/api";
import { useState } from "react";

interface QueryConsoleProps {
	email?: string;
}

export default function QueryConsole({ email }: QueryConsoleProps) {
	const [isSending, setIsSending] = useState(false);
	const [sentQuery, setSentQuery] = useState<string>();
	const [error, setError] = useState<string>();
	// Bumped on each successful send: remounting QueryForm clears the textarea.
	const [sendCount, setSendCount] = useState(0);

	async function handleSubmit(query: string) {
		setError(undefined);
		setSentQuery(undefined);
		setIsSending(true);
		try {
			await submitQuery(query);
			setSentQuery(query);
			setSendCount((count) => count + 1);
		} catch (e) {
			setError(e instanceof Error ? e.message : "Something went wrong");
		} finally {
			setIsSending(false);
		}
	}

	return (
		<div className="flex flex-col gap-6">
			<QueryForm key={sendCount} onSubmit={handleSubmit} disabled={isSending} />

			{error && <p className="text-sm text-red-600">{error}</p>}

			{sentQuery && <QuerySentNotice query={sentQuery} email={email} />}
		</div>
	);
}
