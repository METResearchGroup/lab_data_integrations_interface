'use client'

import { useState } from 'react'
import DataSourceDropdown from '@/components/DataSourceDropdown'
import ParametersInput from '@/components/ParametersInput'
import RunButton from '@/components/RunButton'
import { DataSourceId } from '@/lib/sources'
import { AppState, CollectionParams } from '@/lib/types'

export default function Home() {
  const [source, setSource] = useState<DataSourceId>('bluesky')
  const [params, setParams] = useState<CollectionParams>({ limit: 50 })
  const [appState, setAppState] = useState<AppState>({ status: 'idle' })

  async function handleRun() {
    setAppState({ status: 'running' })
    try {
      // const res = await fetch('/api/collect', {
      //   method: 'POST',
      //   headers: { 'Content-Type': 'application/json' },
      //   body: JSON.stringify({ source, params }),
      // })
      // if (!res.ok) throw new Error(await res.text())
      // const { downloadUrl } = await res.json()
      const downloadUrl = "https://www.image2url.com/r2/default/images/1778351119439-4535f6b3-d0cd-4f4c-ba6b-5549348eebc7.jpg"
      setAppState({ status: 'success', downloadUrl })
    } catch (e) {
      setAppState({ status: 'error', message: e instanceof Error ? e.message : 'Something went wrong' })
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-zinc-50">
      <div className="w-full max-w-lg rounded-xl bg-white p-8 shadow-sm flex flex-col gap-6">
        <DataSourceDropdown value={source} onChange={setSource} />
        <ParametersInput source={source} value={params} onChange={setParams} />
        <RunButton onClick={handleRun} disabled={appState.status === 'running'} />
        {appState.status === 'error' && (
          <p className="text-sm text-red-600">{appState.message}</p>
        )}
      </div>
    </main>
  )
}
