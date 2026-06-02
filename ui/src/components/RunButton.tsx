"use client";

interface RunButtonProps {
	onClick: () => void;
	disabled?: boolean;
}

export default function RunButton({ onClick, disabled }: RunButtonProps) {
	return (
		<button
			type="button"
			onClick={onClick}
			disabled={disabled}
			className="w-full rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
		>
			{disabled ? "Running..." : "Run"}
		</button>
	);
}
