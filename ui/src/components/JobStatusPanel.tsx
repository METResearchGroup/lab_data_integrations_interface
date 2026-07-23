import ProgressBar from "@/components/ProgressBar";
import { STATUS_LABELS } from "@/lib/jobs";
import type { JobStatus } from "@/lib/types";

interface JobStatusPanelProps {
	status: JobStatus;
	message?: string;
}

export default function JobStatusPanel({
	status,
	message,
}: JobStatusPanelProps) {
	return (
		<div className="flex flex-col gap-2">
			<p className="text-sm text-zinc-700">
				{message ?? STATUS_LABELS[status]}
			</p>
			<ProgressBar />
		</div>
	);
}
