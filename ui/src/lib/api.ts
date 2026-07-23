import { mockCreateSearchJob, mockGetJobStatus } from "@/lib/mockApi";
import type {
	CreateJobResponse,
	CreateJobWireResponse,
	JobStatusResponse,
	JobStatusWireResponse,
} from "@/lib/types";

function parseCreateJobResponse(
	data: CreateJobWireResponse,
): CreateJobResponse {
	return {
		jobId: data.job_id,
		requestId: data.request_id,
		status: data.status,
		createdAt: data.created_at,
		statusUrl: data.status_url,
	};
}

function parseJobStatusResponse(
	data: JobStatusWireResponse,
): JobStatusResponse {
	return {
		jobId: data.job_id,
		status: data.status,
		message: data.message,
		createdAt: data.created_at,
		updatedAt: data.updated_at,
		result: data.result
			? {
					resultId: data.result.result_id,
					rowCount: data.result.row_count,
					sizeBytes: data.result.size_bytes,
					format: data.result.format,
					downloadUrl: data.result.download_url,
					expiresAt: data.result.expires_at,
				}
			: undefined,
		error: data.error,
	};
}

export async function createSearchJob(
	query: string,
): Promise<CreateJobResponse> {
	const data = await mockCreateSearchJob(query);
	// TODO(real backend): replace the line above with
	// const res = await fetch(`${BASE_URL}/search/jobs/`, {
	// 	method: "POST",
	// 	headers: { "Content-Type": "application/json" },
	// 	body: JSON.stringify({ query }),
	// });
	// if (!res.ok) throw new Error(await res.text());
	// const data: CreateJobWireResponse = await res.json();
	return parseCreateJobResponse(data);
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
	const data = await mockGetJobStatus(jobId);
	// TODO(real backend): replace the line above with
	// const res = await fetch(`${BASE_URL}/search/jobs/${jobId}`);
	// if (!res.ok) throw new Error(await res.text());
	// const data: JobStatusWireResponse = await res.json();
	return parseJobStatusResponse(data);
}
