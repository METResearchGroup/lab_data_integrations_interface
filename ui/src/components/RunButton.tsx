'use client'

interface RunButtonProps {
  onClick: () => void
}

export default function RunButton({ onClick }: RunButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700"
    >
      Run
    </button>
  )
}
