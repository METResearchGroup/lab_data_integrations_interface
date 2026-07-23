"use client";

import JobErrorNotice from "@/components/JobErrorNotice";
import JobResultSummary from "@/components/JobResultSummary";
import JobStatusPanel from "@/components/JobStatusPanel";
import QueryForm from "@/components/QueryForm";
import { useJobPolling } from "@/hooks/useJobPolling";
import { createSearchJob } from "@/lib/api";
import { useState } from "react";

export default function Home() {
	const [jobId, setJobId] = useState<string>();
	const [createError, setCreateError] = useState<string>();
	const [isCreating, setIsCreating] = useState(false);

	const polling = useJobPolling(jobId);

	async function handleSubmit(query: string) {
		setCreateError(undefined);
		setIsCreating(true);
		try {
			const job = await createSearchJob(query);
			setJobId(job.jobId);
		} catch (e) {
			setCreateError(e instanceof Error ? e.message : "Something went wrong");
		} finally {
			setIsCreating(false);
		}
	}

	const isBusy = isCreating || polling.phase === "polling";
	const isReady = polling.phase === "done" && polling.job.status === "READY";
	const isTerminalError =
		polling.phase === "done" &&
		(polling.job.status === "REJECTED" ||
			polling.job.status === "FAILED" ||
			polling.job.status === "EXPIRED");

	return (
		<main className="flex min-h-screen flex-col items-center justify-center bg-zinc-50">
			<div className="w-full max-w-lg rounded-xl bg-white p-8 shadow-sm flex flex-col gap-6">
				<QueryForm onSubmit={handleSubmit} disabled={isBusy} />

				{createError && <p className="text-sm text-red-600">{createError}</p>}

				{polling.phase === "polling" && (
					<JobStatusPanel
						status={polling.job?.status ?? "PENDING"}
						message={polling.job?.message}
					/>
				)}

				{isReady && polling.phase === "done" && (
					<JobResultSummary job={polling.job} />
				)}
				{isTerminalError && polling.phase === "done" && (
					<JobErrorNotice job={polling.job} />
				)}

				{polling.phase === "error" && (
					<p className="text-sm text-red-600">{polling.message}</p>
				)}
			</div>
		</main>
	);
}
