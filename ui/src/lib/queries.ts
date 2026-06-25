import type { QueryId } from "@/lib/types";

export type QueryDefinition = {
	id: QueryId;
	label: string;
};

export const QUERIES: QueryDefinition[] = [
	{ id: "recent-posts", label: "Recent Posts" },
	{ id: "top-authors", label: "Top Authors" },
];
