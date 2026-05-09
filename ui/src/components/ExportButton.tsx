'use client'

interface ExportButtonProps {
  downloadUrl?: string
}

export default function ExportButton({ downloadUrl }: ExportButtonProps) {
  return (
    <a
      href={downloadUrl}
      download
      aria-disabled={!downloadUrl}
      className="w-full rounded-md border border-zinc-300 px-4 py-2 text-center text-sm font-medium text-zinc-900 hover:bg-zinc-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 aria-disabled:pointer-events-none"
    >
      Export CSV
    </a>
  )
}
