"use client";

import Spinner from "@/components/Spinner";
import { useEffect, useState } from "react";

interface QueryPendingNoticeProps {
	query: string;
	startedAt: number;
}

function formatElapsed(totalSeconds: number): string {
	const seconds = Math.max(0, totalSeconds);
	const minutes = Math.floor(seconds / 60);
	const remainder = seconds % 60;
	if (minutes === 0) return `${remainder}s`;
	return `${minutes}m ${remainder.toString().padStart(2, "0")}s`;
}

export default function QueryPendingNotice({
	query,
	startedAt,
}: QueryPendingNoticeProps) {
	const [elapsedSeconds, setElapsedSeconds] = useState(() =>
		Math.floor((Date.now() - startedAt) / 1000),
	);

	useEffect(() => {
		const tick = () => {
			setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
		};
		tick();
		const id = window.setInterval(tick, 1000);
		return () => window.clearInterval(id);
	}, [startedAt]);

	return (
		<div
			role="status"
			aria-live="polite"
			className="flex flex-col gap-3 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-3"
		>
			<div className="flex items-center gap-2">
				<Spinner className="h-4 w-4 text-zinc-600" />
				<p className="text-sm font-medium text-zinc-800">Sending your query</p>
			</div>
			<p className="text-sm text-zinc-600 italic">“{query}”</p>
			<div className="flex flex-col gap-2" aria-hidden="true">
				<div className="h-3 w-2/3 animate-pulse rounded bg-zinc-200" />
				<div className="h-3 w-full animate-pulse rounded bg-zinc-200" />
				<div className="h-3 w-5/6 animate-pulse rounded bg-zinc-200" />
			</div>
			<p className="text-xs text-zinc-500">
				This can take a moment. Elapsed {formatElapsed(elapsedSeconds)}.
			</p>
		</div>
	);
}
