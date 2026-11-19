"use client";

import Spinner from "@/components/Spinner";

interface RunButtonProps {
	onClick: () => void;
	disabled?: boolean;
	pending?: boolean;
	label?: string;
	pendingLabel?: string;
}

export default function RunButton({
	onClick,
	disabled,
	pending = false,
	label = "Run",
	pendingLabel = "Running...",
}: RunButtonProps) {
	const blocked = disabled || pending;

	return (
		<button
			type="button"
			onClick={() => {
				if (blocked) return;
				onClick();
			}}
			disabled={blocked}
			aria-busy={pending || undefined}
			className={`flex w-full items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium text-white ${
				pending
					? "cursor-wait bg-zinc-800"
					: "bg-zinc-900 hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
			}`}
		>
			{pending && <Spinner />}
			{pending ? pendingLabel : label}
		</button>
	);
}
