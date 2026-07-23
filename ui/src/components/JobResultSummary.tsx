import ExportButton from "@/components/ExportButton";
import { formatBytes, formatDuration } from "@/lib/format";
import type { JobStatusResponse } from "@/lib/types";

interface JobResultSummaryProps {
	job: JobStatusResponse;
}

export default function JobResultSummary({ job }: JobResultSummaryProps) {
	if (!job.result) return null;

	const elapsedMs =
		new Date(job.updatedAt).getTime() - new Date(job.createdAt).getTime();

	return (
		<div className="flex flex-col gap-3">
			<p className="text-sm text-zinc-700">
				{job.message ?? "Your result is ready."}
			</p>
			<dl className="grid grid-cols-3 gap-2 text-center text-sm">
				<div className="rounded-md bg-zinc-50 px-2 py-3">
					<dt className="text-xs text-zinc-400">Records</dt>
					<dd className="font-medium text-zinc-900">
						{job.result.rowCount.toLocaleString()}
					</dd>
				</div>
				<div className="rounded-md bg-zinc-50 px-2 py-3">
					<dt className="text-xs text-zinc-400">Size</dt>
					<dd className="font-medium text-zinc-900">
						{formatBytes(job.result.sizeBytes)}
					</dd>
				</div>
				<div className="rounded-md bg-zinc-50 px-2 py-3">
					<dt className="text-xs text-zinc-400">Time</dt>
					<dd className="font-medium text-zinc-900">
						{formatDuration(elapsedMs)}
					</dd>
				</div>
			</dl>
			<ExportButton downloadUrl={job.result.downloadUrl} />
		</div>
	);
}
