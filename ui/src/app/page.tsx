'use client'

import { useState } from 'react'
import DataSourceDropdown from '@/components/DataSourceDropdown'
import { DataSourceId } from '@/lib/sources'

export default function Home() {
  const [source, setSource] = useState<DataSourceId>('bluesky')

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-zinc-50">
      <div className="w-full max-w-lg rounded-xl bg-white p-8 shadow-sm">
        <DataSourceDropdown value={source} onChange={setSource} />
      </div>
    </main>
  )
}
