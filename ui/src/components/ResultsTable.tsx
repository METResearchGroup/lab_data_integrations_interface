import type { QueryRow } from "@/lib/types";

interface ResultsTableProps {
	rows: QueryRow[];
}

export default function ResultsTable({ rows }: ResultsTableProps) {
	if (rows.length === 0) return null;

	const columns = Object.keys(rows[0]);

	return (
		<div className="overflow-x-auto rounded-md border border-zinc-200">
			<div className="max-h-72 overflow-y-auto">
				<table className="w-full text-left text-sm text-zinc-700">
					<thead className="sticky top-0 bg-zinc-50">
						<tr>
							{columns.map((col) => (
								<th
									key={col}
									className="border-b border-zinc-200 px-3 py-2 font-medium text-zinc-900 whitespace-nowrap"
								>
									{col}
								</th>
							))}
						</tr>
					</thead>
					<tbody>
						{rows.map((row) => (
							<tr
								key={JSON.stringify(row)}
								className="border-b border-zinc-100 last:border-0"
							>
								{columns.map((col) => (
									<td key={col} className="px-3 py-2 whitespace-nowrap">
										{row[col]}
									</td>
								))}
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</div>
	);
}
