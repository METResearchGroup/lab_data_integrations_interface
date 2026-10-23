use bluesky_backfill_app_rust_rewrite::timestamp_utils::{
    CREATED_AT_FORMAT, get_current_timestamp,
};
use chrono::NaiveDateTime;

#[test]
fn current_timestamp_matches_contract_format() {
    let ts = get_current_timestamp();
    assert_eq!(ts.len(), 19);
    assert!(NaiveDateTime::parse_from_str(&ts, CREATED_AT_FORMAT).is_ok());
}
