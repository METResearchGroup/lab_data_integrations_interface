"use client";

import { type DataSourceId, SOURCES } from "@/lib/sources";

interface DataSourceDropdownProps {
	value: DataSourceId;
	onChange: (value: DataSourceId) => void;
}

export default function DataSourceDropdown({
	value,
	onChange,
}: DataSourceDropdownProps) {
	return (
		<div className="flex flex-col gap-1">
			<label
				htmlFor="data-source"
				className="text-sm font-medium text-zinc-700"
			>
				Data Source
			</label>
			<select
				id="data-source"
				value={value}
				onChange={(e) => onChange(e.target.value as DataSourceId)}
				className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
			>
				{SOURCES.map((source) => (
					<option
						key={source.id}
						value={source.id}
						disabled={!source.supported}
					>
						{source.label}
						{!source.supported ? " (coming soon)" : ""}
					</option>
				))}
			</select>
		</div>
	);
}
