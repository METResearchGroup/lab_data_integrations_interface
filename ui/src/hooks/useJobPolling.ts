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

		// Only the first poll clears `job`. Doing it on every iteration would
		// blank the status out mid-poll, and once getJobStatus is a real network
		// call that gap is long enough for React to paint the empty state — the
		// panel would flicker back to PENDING every 1.5s.
		async function poll(isFirstPoll = false) {
			if (isFirstPoll) setState({ phase: "polling" });

			try {
				const job = await getJobStatus(jobId as string);
				if (cancelled) return;
				if (isTerminalStatus(job.status)) {
					setState({ phase: "done", job });
					return;
				}
				setState({ phase: "polling", job });
				timeoutId = setTimeout(() => poll(), POLL_INTERVAL_MS);
			} catch (e) {
				if (cancelled) return;
				setState({
					phase: "error",
					message: e instanceof Error ? e.message : "Something went wrong",
				});
			}
		}

		poll(true);

		return () => {
			cancelled = true;
			if (timeoutId) clearTimeout(timeoutId);
		};
	}, [jobId]);

	return state;
}
