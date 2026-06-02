export type DataSource = {
	id: string;
	label: string;
	supported: boolean;
};

export const SOURCES: DataSource[] = [
	{ id: "bluesky", label: "Bluesky", supported: true },
	{ id: "reddit", label: "Reddit", supported: false },
	{ id: "twitter", label: "Twitter / X", supported: false },
];

export type DataSourceId = (typeof SOURCES)[number]["id"];
