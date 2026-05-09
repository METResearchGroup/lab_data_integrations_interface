'use client'

import { useState } from 'react'
import DataSourceDropdown from '@/components/DataSourceDropdown'
import ParametersInput from '@/components/ParametersInput'
import RunButton from '@/components/RunButton'
import { DataSourceId } from '@/lib/sources'
import { CollectionParams } from '@/lib/types'

export default function Home() {
  const [source, setSource] = useState<DataSourceId>('bluesky')
  const [params, setParams] = useState<CollectionParams>({ limit: 50 })

  function handleRun() {
    console.log({ source, params })
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-zinc-50">
      <div className="w-full max-w-lg rounded-xl bg-white p-8 shadow-sm flex flex-col gap-6">
        <DataSourceDropdown value={source} onChange={setSource} />
        <ParametersInput source={source} value={params} onChange={setParams} />
        <RunButton onClick={handleRun} />
      </div>
    </main>
  )
}
