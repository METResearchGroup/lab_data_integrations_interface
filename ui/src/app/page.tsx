"use client";

import { useState } from "react";
import DataSourceDropdown from "@/components/DataSourceDropdown";
import ParametersInput from "@/components/ParametersInput";
import RunButton from "@/components/RunButton";
import ExportButton from "@/components/ExportButton";
import ProgressBar from "@/components/ProgressBar";
import { DataSourceId } from "@/lib/sources";
import { AppState, CollectionParams } from "@/lib/types";
import { DEFAULT_LIMIT } from "@/lib/constants";

export default function Home() {
  const [source, setSource] = useState<DataSourceId>("bluesky");
  const [params, setParams] = useState<CollectionParams>({ limit: DEFAULT_LIMIT });
  const [appState, setAppState] = useState<AppState>({ status: "idle" });

  async function handleRun() {
    if (appState.status === "running") return;
    if (!params.limit || params.limit < 1) {
      setAppState({ status: "error", message: "Please enter in the number of results field with at least 1" });
      return;
    }
    setAppState({ status: "running" });
    try {
      // const res = await fetch('/api/collect', {
      //   method: 'POST',
      //   headers: { 'Content-Type': 'application/json' },
      //   body: JSON.stringify({ source, params }),
      // })
      // if (!res.ok) throw new Error(await res.text())
      // const { downloadUrl } = await res.json()
      await new Promise((resolve) => setTimeout(resolve, 5000));
      const blob = new Blob(
        [
          "uri,url,author_handle,text,created_at\ntest-uri,https://bsky.app,user.bsky.social,hello world,2024-01-01",
        ],
        { type: "text/csv" },
      );
      const downloadUrl = URL.createObjectURL(blob);
      setAppState({ status: "success", downloadUrl });
    } catch (e) {
      setAppState({
        status: "error",
        message: e instanceof Error ? e.message : "Something went wrong",
      });
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-zinc-50">
      <div className="w-full max-w-lg rounded-xl bg-white p-8 shadow-sm flex flex-col gap-6">
        <DataSourceDropdown value={source} onChange={setSource} />

        <ParametersInput
          source={source}
          value={params}
          onChange={setParams}
          onLimitFocus={() => setAppState({ status: "idle" })}
        />

        <RunButton
          onClick={handleRun}
          disabled={appState.status === "running"}
        />

        {appState.status === "running" && <ProgressBar />}

        <ExportButton
          downloadUrl={
            appState.status === "success" ? appState.downloadUrl : undefined
          }
        />
        
        {appState.status === "error" && (
          <p className="text-sm text-red-600">{appState.message}</p>
        )}
      </div>
    </main>
  );
}
