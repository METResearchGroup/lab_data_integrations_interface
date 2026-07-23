import { STATUS_LABELS } from "@/lib/jobs";
import type { JobStatusResponse } from "@/lib/types";

interface JobErrorNoticeProps {
	job: JobStatusResponse;
}

export default function JobErrorNotice({ job }: JobErrorNoticeProps) {
	return (
		<div className="flex flex-col gap-1 rounded-md border border-red-200 bg-red-50 px-3 py-3">
			<p className="text-sm font-medium text-red-800">
				{STATUS_LABELS[job.status]}
			</p>
			<p className="text-sm text-red-700">
				{job.error?.message ?? "This request could not be completed."}
			</p>
			{job.error?.code && (
				<p className="text-xs text-red-400">{job.error.code}</p>
			)}
		</div>
	);
}
