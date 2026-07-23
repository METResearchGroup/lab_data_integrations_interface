import type {
	CreateJobWireResponse,
	JobStatus,
	JobStatusWireResponse,
} from "@/lib/types";

const PROGRESSION: JobStatus[] = [
	"PENDING",
	"ROUTING",
	"GENERATING_SQL",
	"VALIDATING",
	"ESTIMATING_COST",
	"QUEUED",
	"EXECUTING",
	"POSTPROCESSING",
];
const STEP_MS = 700;

type MockOutcome = "READY" | "REJECTED" | "FAILED";

type MockJob = {
	jobId: string;
	requestId: string;
	query: string;
	outcome: MockOutcome;
	createdAt: number;
};

const jobs = new Map<string, MockJob>();

function randomId(prefix: string): string {
	return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function pickOutcome(query: string): MockOutcome {
	const lower = query.toLowerCase();
	if (lower.includes("reject")) return "REJECTED";
	if (lower.includes("fail")) return "FAILED";
	return "READY";
}

function hashString(value: string): number {
	let hash = 0;
	for (let i = 0; i < value.length; i++) {
		hash = (hash * 31 + value.charCodeAt(i)) | 0;
	}
	return Math.abs(hash);
}

function buildReadyResult(job: MockJob) {
	const hash = hashString(job.query);
	const rowCount = 100 + (hash % 25000);
	const csv = `query\n"${job.query.replace(/"/g, '""')}"\n`;
	const blob = new Blob([csv], { type: "text/csv" });
	return {
		result_id: randomId("result"),
		row_count: rowCount,
		size_bytes: blob.size,
		format: "csv",
		download_url: URL.createObjectURL(blob),
		expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
	};
}

export async function mockCreateSearchJob(
	query: string,
): Promise<CreateJobWireResponse> {
	const jobId = randomId("job");
	const requestId = randomId("req");
	const createdAt = Date.now();
	jobs.set(jobId, {
		jobId,
		requestId,
		query,
		outcome: pickOutcome(query),
		createdAt,
	});
	return {
		job_id: jobId,
		request_id: requestId,
		status: "PENDING",
		created_at: new Date(createdAt).toISOString(),
		status_url: `/search/jobs/${jobId}`,
	};
}

export async function mockGetJobStatus(
	jobId: string,
): Promise<JobStatusWireResponse> {
	const job = jobs.get(jobId);
	if (!job) throw new Error(`Unknown job: ${jobId}`);

	const elapsed = Date.now() - job.createdAt;
	const terminalAt = job.createdAt + PROGRESSION.length * STEP_MS;

	if (elapsed < PROGRESSION.length * STEP_MS) {
		const stepIndex = Math.floor(elapsed / STEP_MS);
		const status = PROGRESSION[stepIndex];
		return {
			job_id: job.jobId,
			status,
			created_at: new Date(job.createdAt).toISOString(),
			updated_at: new Date(job.createdAt + stepIndex * STEP_MS).toISOString(),
		};
	}

	const updatedAt = new Date(terminalAt).toISOString();
	const createdAtIso = new Date(job.createdAt).toISOString();

	if (job.outcome === "READY") {
		return {
			job_id: job.jobId,
			status: "READY",
			message: "Your result is ready.",
			created_at: createdAtIso,
			updated_at: updatedAt,
			result: buildReadyResult(job),
		};
	}

	if (job.outcome === "REJECTED") {
		return {
			job_id: job.jobId,
			status: "REJECTED",
			created_at: createdAtIso,
			updated_at: updatedAt,
			error: {
				code: "QUERY_TOO_EXPENSIVE",
				message:
					"This request is too large for automatic execution. Try narrowing the date range or selecting fewer fields.",
			},
		};
	}

	return {
		job_id: job.jobId,
		status: "FAILED",
		created_at: createdAtIso,
		updated_at: updatedAt,
		error: {
			code: "INTERNAL_ERROR",
			message: "Your request failed to be processed.",
		},
	};
}
