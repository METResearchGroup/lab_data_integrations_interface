use bluesky_backfill_app_rust_rewrite::constants::{
    BLUESKY_START_DATE, DATA_END_DATE, RecordType, record_type_for_collection,
};
use chrono::NaiveDate;

#[test]
fn post_collection_maps_to_posts() {
    assert_eq!(
        record_type_for_collection("app.bsky.feed.post"),
        Some(RecordType::Posts),
    );
}

#[test]
fn like_collection_maps_to_likes() {
    assert_eq!(
        record_type_for_collection("app.bsky.feed.like"),
        Some(RecordType::Likes)
    );
}

#[test]
fn repost_collection_maps_to_reposts() {
    assert_eq!(
        record_type_for_collection("app.bsky.feed.repost"),
        Some(RecordType::Reposts),
    );
}

#[test]
fn follow_collection_maps_to_follows() {
    assert_eq!(
        record_type_for_collection("app.bsky.graph.follow"),
        Some(RecordType::Follows),
    );
}

#[test]
fn unknown_collection_maps_to_none() {
    assert_eq!(record_type_for_collection("app.bsky.actor.profile"), None);
}

#[test]
fn as_str_matches_python_values() {
    assert_eq!(RecordType::Posts.as_str(), "posts");
    assert_eq!(RecordType::Likes.as_str(), "likes");
    assert_eq!(RecordType::Reposts.as_str(), "reposts");
    assert_eq!(RecordType::Follows.as_str(), "follows");
}

#[test]
fn bluesky_start_and_end_dates() {
    assert_eq!(DATA_END_DATE, NaiveDate::from_ymd_opt(2026, 8, 7).unwrap());
    assert_eq!(
        BLUESKY_START_DATE,
        NaiveDate::from_ymd_opt(2022, 11, 17).unwrap()
    );
}
