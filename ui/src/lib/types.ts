export type CollectionParams = {
	limit: number;
	handles?: string[];
};

export type AppState =
	| { status: "idle" }
	| { status: "running" }
	| { status: "success"; downloadUrl: string }
	| { status: "error"; message: string };

export type QueryId = "recent-posts" | "top-authors";

export type QueryRow = Record<string, string>;

export type QueryState =
	| { status: "idle" }
	| { status: "running" }
	| { status: "success"; rows: QueryRow[]; downloadUrl: string }
	| { status: "error"; message: string };
