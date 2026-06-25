import type { QueryId, QueryRow } from "@/lib/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const DATASET_ID = "bluesky_9ea63f70-e9a2-4033-887d-97dcc43a0dc2";

const ROUTE: Record<QueryId, string> = {
	"recent-posts": "/posts/recent",
	"top-authors": "/posts/top-authors",
};

export type QueryResponse = {
	rows: QueryRow[];
	downloadUrl: string;
};

export async function runQuery(queryId: QueryId): Promise<QueryResponse> {
	const params = new URLSearchParams({ dataset_id: DATASET_ID });
	const res = await fetch(`${BASE_URL}${ROUTE[queryId]}?${params}`);
	if (!res.ok) throw new Error(await res.text());
	const data = await res.json();
	return { rows: data.rows, downloadUrl: data.download_url };
}
