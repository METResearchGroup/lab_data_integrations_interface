"use client";

import { QUERIES } from "@/lib/queries";
import type { QueryId } from "@/lib/types";

interface QuerySelectorProps {
	value: QueryId;
	onChange: (id: QueryId) => void;
}

export default function QuerySelector({ value, onChange }: QuerySelectorProps) {
	return (
		<div className="flex gap-2">
			{QUERIES.map((q) => (
				<button
					key={q.id}
					type="button"
					onClick={() => onChange(q.id)}
					className={`flex-1 rounded-md border px-4 py-2 text-sm font-medium transition-colors ${
						value === q.id
							? "border-zinc-900 bg-zinc-900 text-white"
							: "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50"
					}`}
				>
					{q.label}
				</button>
			))}
		</div>
	);
}
