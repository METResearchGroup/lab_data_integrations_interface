import QueryConsole from "@/components/QueryConsole";
import { createClient } from "@/lib/supabase/server";

export default async function Home() {
	// Shown in the confirmation, so the user knows where results will land.
	const supabase = await createClient();
	const {
		data: { user },
	} = await supabase.auth.getUser();

	return (
		<main className="flex flex-1 flex-col items-center justify-center bg-zinc-50">
			<div className="w-full max-w-lg rounded-xl bg-white p-8 shadow-sm">
				<QueryConsole email={user?.email} />
			</div>
		</main>
	);
}
