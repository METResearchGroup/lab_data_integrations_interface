"use client";

import DataSourceDropdown from "@/components/DataSourceDropdown";
import ExportButton from "@/components/ExportButton";
import ParametersInput from "@/components/ParametersInput";
import ProgressBar from "@/components/ProgressBar";
import QuerySelector from "@/components/QuerySelector";
import ResultsTable from "@/components/ResultsTable";
import RunButton from "@/components/RunButton";
import { runQuery } from "@/lib/api";
import { DEFAULT_LIMIT } from "@/lib/constants";
import type { DataSourceId } from "@/lib/sources";
import type { CollectionParams, QueryId, QueryState } from "@/lib/types";
import { useState } from "react";

export default function Home() {
	const [source, setSource] = useState<DataSourceId>("bluesky");
	const [params, setParams] = useState<CollectionParams>({
		limit: DEFAULT_LIMIT,
	});
	const [queryId, setQueryId] = useState<QueryId>("recent-posts");
	const [queryState, setQueryState] = useState<QueryState>({ status: "idle" });

	async function handleRun() {
		if (queryState.status === "running") return;
		setQueryState({ status: "running" });
		try {
			const { rows, downloadUrl } = await runQuery(queryId);
			setQueryState({ status: "success", rows, downloadUrl });
		} catch (e) {
			setQueryState({
				status: "error",
				message: e instanceof Error ? e.message : "Something went wrong",
			});
		}
	}

	return (
		<main className="flex min-h-screen flex-col items-center justify-center bg-zinc-50">
			<div className="w-full max-w-lg rounded-xl bg-white p-8 shadow-sm flex flex-col gap-6">
				<DataSourceDropdown value={source} onChange={setSource} />

				<ParametersInput source={source} value={params} onChange={setParams} />

				<div className="flex flex-col gap-2">
					<label className="text-sm font-medium text-zinc-700">
						Choose query{" "}
						<span className="font-normal text-zinc-400">(select one)</span>
					</label>
					<QuerySelector value={queryId} onChange={setQueryId} />
				</div>

				<hr className="border-zinc-200" />

				<div className="mt-4">
					<RunButton
						onClick={handleRun}
						disabled={queryState.status === "running"}
					/>
				</div>

				{queryState.status === "running" && <ProgressBar />}

				{queryState.status === "success" && (
					<ResultsTable rows={queryState.rows} />
				)}

				<ExportButton
					downloadUrl={
						queryState.status === "success" && queryState.downloadUrl
							? queryState.downloadUrl
							: undefined
					}
				/>

				{queryState.status === "error" && (
					<p className="text-sm text-red-600">{queryState.message}</p>
				)}
			</div>
		</main>
	);
}
