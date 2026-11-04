"use client";

import QueryForm from "@/components/QueryForm";
import QueryPendingNotice from "@/components/QueryPendingNotice";
import QuerySentNotice from "@/components/QuerySentNotice";
import { submitQuery } from "@/lib/api";
import { useRef, useState } from "react";

interface QueryConsoleProps {
	email?: string;
}

export default function QueryConsole({ email }: QueryConsoleProps) {
	const [isSending, setIsSending] = useState(false);
	const [pendingQuery, setPendingQuery] = useState<string>();
	const [startedAt, setStartedAt] = useState<number>();
	const [sentQuery, setSentQuery] = useState<string>();
	const [error, setError] = useState<string>();
	// Bumped on each successful send: remounting QueryForm clears the textarea.
	const [sendCount, setSendCount] = useState(0);
	// State updates are async, so a second click in the same turn can pass an
	// isSending check. The ref closes that window.
	const sendingRef = useRef(false);

	async function handleSubmit(query: string) {
		if (sendingRef.current) return;
		sendingRef.current = true;

		setError(undefined);
		setSentQuery(undefined);
		setPendingQuery(query);
		setStartedAt(Date.now());
		setIsSending(true);
		try {
			await submitQuery(query);
			setSentQuery(query);
			setSendCount((count) => count + 1);
		} catch (e) {
			setError(e instanceof Error ? e.message : "Something went wrong");
		} finally {
			sendingRef.current = false;
			setIsSending(false);
			setPendingQuery(undefined);
			setStartedAt(undefined);
		}
	}

	return (
		<div className="flex flex-col gap-6">
			<QueryForm key={sendCount} onSubmit={handleSubmit} disabled={isSending} />

			{isSending && pendingQuery && startedAt !== undefined && (
				<QueryPendingNotice query={pendingQuery} startedAt={startedAt} />
			)}

			{error && (
				<div
					role="alert"
					className="flex flex-col gap-1 rounded-md border border-red-200 bg-red-50 px-3 py-3"
				>
					<p className="text-sm font-medium text-red-800">
						Could not send the query
					</p>
					<p className="text-sm text-red-700">{error}</p>
				</div>
			)}

			{sentQuery && <QuerySentNotice query={sentQuery} email={email} />}
		</div>
	);
}
