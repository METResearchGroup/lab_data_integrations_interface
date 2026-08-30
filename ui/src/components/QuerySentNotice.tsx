interface QuerySentNoticeProps {
	query: string;
	email?: string;
}

export default function QuerySentNotice({
	query,
	email,
}: QuerySentNoticeProps) {
	return (
		<div className="flex flex-col gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-3">
			<p className="text-sm font-medium text-emerald-800">Query sent</p>
			<p className="text-sm text-emerald-700 italic">“{query}”</p>
			<p className="text-sm text-emerald-700">
				Results go to {email ?? "your email"} when the query finishes. You do
				not need to keep this page open.
			</p>
		</div>
	);
}
