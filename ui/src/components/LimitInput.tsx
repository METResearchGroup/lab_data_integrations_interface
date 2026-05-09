"use client";

interface LimitInputProps {
  value: number;
  onChange: (value: number) => void;
}

export default function LimitInput({ value, onChange }: LimitInputProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor="limit" className="text-sm font-medium text-zinc-700">
        Number of Results
      </label>
      <input
        id="limit"
        type="number"
        min={1}
        value={value}
        onChange={(e) => onChange(parseInt(e.target.value, 10))}
        className="rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-900 shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500"
      />
    </div>
  );
}
