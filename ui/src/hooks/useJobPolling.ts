import { getJobStatus } from "@/lib/api";
import { POLL_INTERVAL_MS } from "@/lib/constants";
import { isTerminalStatus } from "@/lib/jobs";
import type { JobStatusResponse } from "@/lib/types";
import { useEffect, useState } from "react";

export type JobPollingState =
	| { phase: "idle" }
	| { phase: "polling"; job?: JobStatusResponse }
	| { phase: "done"; job: JobStatusResponse }
	| { phase: "error"; message: string };

export function useJobPolling(jobId: string | undefined): JobPollingState {
	const [state, setState] = useState<JobPollingState>({ phase: "idle" });

	useEffect(() => {
		if (!jobId) return;

		let cancelled = false;
		let timeoutId: ReturnType<typeof setTimeout> | undefined;

		async function poll() {
			setState({ phase: "polling" });
			try {
				const job = await getJobStatus(jobId as string);
				if (cancelled) return;
				if (isTerminalStatus(job.status)) {
					setState({ phase: "done", job });
					return;
				}
				setState({ phase: "polling", job });
				timeoutId = setTimeout(poll, POLL_INTERVAL_MS);
			} catch (e) {
				if (cancelled) return;
				setState({
					phase: "error",
					message: e instanceof Error ? e.message : "Something went wrong",
				});
			}
		}

		poll();

		return () => {
			cancelled = true;
			if (timeoutId) clearTimeout(timeoutId);
		};
	}, [jobId]);

	return state;
}
