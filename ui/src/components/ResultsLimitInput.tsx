"use client";

import { DEFAULT_LIMIT } from "@/lib/constants";
import { useState } from "react";

interface ResultsLimitInputProps {
	value: number;
	onChange: (value: number) => void;
	onFocus?: () => void;
}

export default function ResultsLimitInput({
	value,
	onChange,
	onFocus,
}: ResultsLimitInputProps) {
	const [raw, setRaw] = useState(String(value));

	function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
		setRaw(e.target.value);
		const parsed = Number.parseInt(e.target.value, 10);
		if (!Number.isNaN(parsed) && parsed >= 1) {
			onChange(parsed);
		}
	}

	function handleBlur() {
		const parsed = Number.parseInt(raw, 10);
		if (Number.isNaN(parsed) || parsed < 1) {
			setRaw(String(DEFAULT_LIMIT));
			onChange(DEFAULT_LIMIT);
		}
	}

	return (
		<div className="flex flex-col gap-1">
			<label htmlFor="limit" className="text-sm font-medium text-zinc-700">
				Number of Results
			</label>
			<input
				id="limit"
				type="number"
				min={1}
				value={raw}
				onChange={handleChange}
				onBlur={handleBlur}
				onFocus={onFocus}
				className="rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-900 shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
			/>
		</div>
	);
}
