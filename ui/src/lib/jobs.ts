import type { JobStatus } from "@/lib/types";

export const TERMINAL_JOB_STATUSES: readonly JobStatus[] = [
	"READY",
	"REJECTED",
	"FAILED",
	"EXPIRED",
];

export function isTerminalStatus(status: JobStatus): boolean {
	return TERMINAL_JOB_STATUSES.includes(status);
}

export const STATUS_LABELS: Record<JobStatus, string> = {
	PENDING: "Waiting to start.",
	ROUTING: "Understanding your request.",
	GENERATING_SQL: "Drafting a query for your request.",
	VALIDATING: "Validating the generated query.",
	ESTIMATING_COST: "Estimating query cost.",
	QUEUED: "Queued for execution.",
	EXECUTING: "Running your query.",
	POSTPROCESSING: "Preparing your results.",
	READY: "Your result is ready.",
	REJECTED: "Your request was rejected.",
	FAILED: "Your request failed.",
	EXPIRED: "This result has expired.",
};
