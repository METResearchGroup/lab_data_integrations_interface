"use client";

import RunButton from "@/components/RunButton";
import { validateQuery } from "@/lib/validation";
import { useState } from "react";

interface QueryFormProps {
	onSubmit: (query: string) => void;
	disabled?: boolean;
}

export default function QueryForm({ onSubmit, disabled }: QueryFormProps) {
	const [query, setQuery] = useState("");
	const [error, setError] = useState<string>();

	function handleSubmit() {
		const validationError = validateQuery(query);
		if (validationError) {
			setError(validationError);
			return;
		}
		setError(undefined);
		onSubmit(query.trim());
	}

	return (
		<div className="flex flex-col gap-2">
			<label className="text-sm font-medium text-zinc-700" htmlFor="nl-query">
				Describe the data you want
			</label>
			<textarea
				id="nl-query"
				value={query}
				onChange={(e) => setQuery(e.target.value)}
				disabled={disabled}
				rows={4}
				placeholder="e.g. All posts liked by Stanley in the past two weeks"
				className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 disabled:cursor-not-allowed disabled:opacity-50"
			/>
			<p className="text-xs text-zinc-400">
				Large or ambiguous requests may be rejected or asked to be narrowed
				before they run.
			</p>
			{error && <p className="text-sm text-red-600">{error}</p>}
			<RunButton
				onClick={handleSubmit}
				disabled={disabled}
				label="Search"
				pendingLabel="Searching..."
			/>
		</div>
	);
}
