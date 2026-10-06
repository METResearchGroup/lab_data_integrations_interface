use chrono::NaiveDate;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum RecordType {
    Posts,
    Likes,
    Reposts,
    Follows,
}

impl RecordType {
    pub fn as_str(self) -> &'static str {
        match self {
            RecordType::Posts => "posts",
            RecordType::Likes => "likes",
            RecordType::Reposts => "reposts",
            RecordType::Follows => "follows",
        }
    }
}

pub const RECORD_TYPES: [RecordType; 4] = [
    RecordType::Posts,
    RecordType::Likes,
    RecordType::Reposts,
    RecordType::Follows,
];

pub fn record_type_for_collection(collection: &str) -> Option<RecordType> {
    match collection {
        "app.bsky.feed.post" => Some(RecordType::Posts),
        "app.bsky.feed.like" => Some(RecordType::Likes),
        "app.bsky.feed.repost" => Some(RecordType::Reposts),
        "app.bsky.graph.follow" => Some(RecordType::Follows),
        _ => None,
    }
}

pub const BLUESKY_START_DATE: NaiveDate = NaiveDate::from_ymd_opt(2022, 11, 17).unwrap();
pub const DATA_END_DATE: NaiveDate = NaiveDate::from_ymd_opt(2026, 8, 7).unwrap();
