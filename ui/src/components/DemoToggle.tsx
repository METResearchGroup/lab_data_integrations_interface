"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

export default function DemoToggle() {
	const pathname = usePathname();
	const isDemo = useSearchParams().get("demo") === "1";

	return (
		<Link
			href={isDemo ? pathname : `${pathname}?demo=1`}
			role="switch"
			aria-checked={isDemo}
			className="flex items-center gap-2 text-sm font-medium text-zinc-500 hover:text-zinc-900"
		>
			Demo mode
			<span
				className={`flex h-5 w-9 items-center rounded-full p-0.5 transition-colors ${isDemo ? "bg-zinc-900" : "bg-zinc-300"}`}
			>
				<span
					className={`h-4 w-4 rounded-full bg-white transition-transform ${isDemo ? "translate-x-4" : ""}`}
				/>
			</span>
		</Link>
	);
}
