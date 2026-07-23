export type JobStatus =
	| "PENDING"
	| "ROUTING"
	| "GENERATING_SQL"
	| "VALIDATING"
	| "ESTIMATING_COST"
	| "QUEUED"
	| "EXECUTING"
	| "POSTPROCESSING"
	| "READY"
	| "REJECTED"
	| "FAILED"
	| "EXPIRED";

export type CreateJobWireResponse = {
	job_id: string;
	request_id: string;
	status: JobStatus;
	created_at: string;
	status_url: string;
};

export type JobStatusWireResponse = {
	job_id: string;
	status: JobStatus;
	message?: string;
	created_at: string;
	updated_at: string;
	result?: {
		result_id: string;
		row_count: number;
		size_bytes: number;
		format: string;
		download_url: string;
		expires_at: string;
	};
	error?: { code: string; message: string };
};

export type JobResult = {
	resultId: string;
	rowCount: number;
	sizeBytes: number;
	format: string;
	downloadUrl: string;
	expiresAt: string;
};

export type JobError = { code: string; message: string };

export type CreateJobResponse = {
	jobId: string;
	requestId: string;
	status: JobStatus;
	createdAt: string;
	statusUrl: string;
};

export type JobStatusResponse = {
	jobId: string;
	status: JobStatus;
	message?: string;
	createdAt: string;
	updatedAt: string;
	result?: JobResult;
	error?: JobError;
};
