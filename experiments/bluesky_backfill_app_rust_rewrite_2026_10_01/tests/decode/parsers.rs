use bluesky_backfill_app_rust_rewrite::decode::parsers::{
    lenient, parse_created_at, parse_follow, parse_like_or_repost, parse_post,
};
use chrono::SecondsFormat;
use serde::Deserialize;
use serde_json::{Value, json};

fn cbor(value: Value) -> Vec<u8> {
    serde_ipld_dagcbor::to_vec(&value).unwrap()
}

// Same rendering as Python's `parse_created_at(s).isoformat()`, with `Z` for `+00:00`.
fn created_at(value: &str) -> Option<String> {
    parse_created_at(value).map(|dt| dt.to_rfc3339_opts(SecondsFormat::Micros, true))
}

#[derive(Debug, Deserialize, PartialEq)]
struct Inner<'a> {
    #[serde(default, borrow, deserialize_with = "lenient")]
    uri: Option<&'a str>,
}

#[derive(Debug, Deserialize, PartialEq)]
struct Probe<'a> {
    #[serde(default, borrow, deserialize_with = "lenient")]
    name: Option<&'a str>,
    #[serde(default, deserialize_with = "lenient")]
    count: Option<u64>,
    #[serde(default, borrow, deserialize_with = "lenient")]
    inner: Option<Inner<'a>>,
}

fn probe(bytes: &[u8]) -> Probe<'_> {
    serde_ipld_dagcbor::from_slice(bytes).unwrap()
}

#[test]
fn lenient_keeps_right_typed_fields() {
    let bytes = cbor(json!({"name": "a", "count": 3, "inner": {"uri": "at://x"}}));
    assert_eq!(
        probe(&bytes),
        Probe {
            name: Some("a"),
            count: Some(3),
            inner: Some(Inner {
                uri: Some("at://x")
            }),
        },
    );
}

#[test]
fn lenient_nulls_wrong_typed_fields() {
    let bytes = cbor(json!({"name": 5, "count": "3", "inner": "junk"}));
    assert_eq!(
        probe(&bytes),
        Probe {
            name: None,
            count: None,
            inner: None,
        },
    );
}

#[test]
fn lenient_nulls_missing_and_null_fields() {
    let bytes = cbor(json!({"name": null}));
    assert_eq!(
        probe(&bytes),
        Probe {
            name: None,
            count: None,
            inner: None,
        },
    );
}

#[test]
fn lenient_skips_nested_junk_without_breaking_siblings() {
    let bytes = cbor(json!({"name": {"deep": [1, {"x": "y"}]}, "count": 7, "inner": [1, 2]}));
    assert_eq!(
        probe(&bytes),
        Probe {
            name: None,
            count: Some(7),
            inner: None,
        },
    );
}

#[test]
fn lenient_nulls_wrong_typed_field_inside_right_typed_struct() {
    let bytes = cbor(json!({"inner": {"uri": 5}}));
    assert_eq!(probe(&bytes).inner, Some(Inner { uri: None }));
}

#[test]
fn created_at_utc_designator() {
    assert_eq!(
        created_at("2024-03-01T12:00:00Z").as_deref(),
        Some("2024-03-01T12:00:00.000000Z")
    );
}

#[test]
fn created_at_converts_offsets_to_utc() {
    assert_eq!(
        created_at("2024-03-01T12:00:00+00:00").as_deref(),
        Some("2024-03-01T12:00:00.000000Z")
    );
    assert_eq!(
        created_at("2024-03-01T07:00:00-05:00").as_deref(),
        Some("2024-03-01T12:00:00.000000Z")
    );
}

#[test]
fn created_at_truncates_fraction_to_microseconds() {
    assert_eq!(
        created_at("2024-03-01T12:00:00.123Z").as_deref(),
        Some("2024-03-01T12:00:00.123000Z")
    );
    assert_eq!(
        created_at("2024-03-01T12:00:00.1234567Z").as_deref(),
        Some("2024-03-01T12:00:00.123456Z")
    );
    assert_eq!(
        created_at("2024-03-01T12:00:00.123456789Z").as_deref(),
        Some("2024-03-01T12:00:00.123456Z")
    );
}

#[test]
fn created_at_space_separator() {
    assert_eq!(
        created_at("2024-03-01 12:00:00Z").as_deref(),
        Some("2024-03-01T12:00:00.000000Z")
    );
}

#[test]
fn created_at_rejects_garbage() {
    for value in [
        "",
        "not a date",
        "2024-13-01T00:00:00Z",
        "2024-03-01T24:00:00Z",
    ] {
        assert_eq!(created_at(value), None, "{value:?}");
    }
}

#[test]
#[ignore = "non-RFC 3339 forms Python accepts; decide after the bench Parquet diff"]
fn created_at_python_only_forms() {
    for (value, expected) in [
        ("2024-03-01T12:00:00", "2024-03-01T12:00:00.000000Z"),
        ("2024-03-01", "2024-03-01T00:00:00.000000Z"),
        ("2024-03-01T12:00Z", "2024-03-01T12:00:00.000000Z"),
        ("2024-03-01T12Z", "2024-03-01T12:00:00.000000Z"),
        ("2024-03-01T12:00:00+0530", "2024-03-01T06:30:00.000000Z"),
        ("2024-03-01T12:00:00,5Z", "2024-03-01T12:00:00.500000Z"),
        ("2024-03-01T12:00:00 Z", "2024-03-01T12:00:00.000000Z"),
        ("20240301T120000Z", "2024-03-01T12:00:00.000000Z"),
        ("2024-W09-5", "2024-03-01T00:00:00.000000Z"),
    ] {
        assert_eq!(created_at(value).as_deref(), Some(expected), "{value:?}");
    }
}

#[test]
fn post_full_record() {
    let bytes = cbor(json!({
        "$type": "app.bsky.feed.post",
        "text": "hello",
        "langs": ["en", "ja"],
        "createdAt": "2024-03-01T12:00:00Z",
        "reply": {
            "root": {"uri": "at://did:plc:a/app.bsky.feed.post/1", "cid": "bafyroot"},
            "parent": {"uri": "at://did:plc:b/app.bsky.feed.post/2", "cid": "bafyparent"},
        },
        "embed": {"$type": "app.bsky.embed.images", "images": [{"alt": "x"}]},
    }));
    let post = parse_post(&bytes).unwrap();
    assert_eq!(
        post.created_at
            .map(|dt| dt.to_rfc3339_opts(SecondsFormat::Secs, true))
            .as_deref(),
        Some("2024-03-01T12:00:00Z"),
    );
    assert_eq!(post.text, Some("hello"));
    assert_eq!(post.langs, Some(vec!["en", "ja"]));
    assert_eq!(
        post.reply_root_uri,
        Some("at://did:plc:a/app.bsky.feed.post/1")
    );
    assert_eq!(
        post.reply_parent_uri,
        Some("at://did:plc:b/app.bsky.feed.post/2")
    );
    assert_eq!(post.embed_type, Some("app.bsky.embed.images"));
}

#[test]
fn post_text_borrows_from_record_bytes() {
    let bytes = cbor(json!({"text": "hello", "createdAt": "2024-03-01T12:00:00Z"}));
    let text = parse_post(&bytes).unwrap().text.unwrap();
    assert!(bytes.as_ptr_range().contains(&text.as_ptr()));
}

#[test]
fn post_top_level_has_null_reply_and_embed() {
    let bytes = cbor(json!({"text": "hi", "createdAt": "2024-03-01T12:00:00Z"}));
    let post = parse_post(&bytes).unwrap();
    assert_eq!(post.reply_root_uri, None);
    assert_eq!(post.reply_parent_uri, None);
    assert_eq!(post.embed_type, None);
    assert_eq!(post.langs, None);
}

#[test]
fn post_langs_drops_non_string_members() {
    let bytes = cbor(json!({"langs": ["en", 5, null, {"x": 1}, "ja"]}));
    assert_eq!(parse_post(&bytes).unwrap().langs, Some(vec!["en", "ja"]));
}

#[test]
fn post_langs_wrong_type_is_null() {
    let bytes = cbor(json!({"langs": "en"}));
    assert_eq!(parse_post(&bytes).unwrap().langs, None);
}

#[test]
fn post_empty_langs_stays_empty() {
    let bytes = cbor(json!({"langs": []}));
    assert_eq!(parse_post(&bytes).unwrap().langs, Some(vec![]));
}

#[test]
fn post_wrong_typed_fields_are_null() {
    let bytes = cbor(json!({
        "text": 5,
        "createdAt": 1700000000,
        "reply": "junk",
        "embed": 5,
    }));
    let post = parse_post(&bytes).unwrap();
    assert_eq!(post.text, None);
    assert_eq!(post.created_at, None);
    assert_eq!(post.reply_root_uri, None);
    assert_eq!(post.reply_parent_uri, None);
    assert_eq!(post.embed_type, None);
}

#[test]
fn post_reply_with_wrong_typed_root_keeps_parent() {
    let bytes = cbor(json!({
        "reply": {
            "root": "junk",
            "parent": {"uri": "at://did:plc:b/app.bsky.feed.post/2"},
        },
    }));
    let post = parse_post(&bytes).unwrap();
    assert_eq!(post.reply_root_uri, None);
    assert_eq!(
        post.reply_parent_uri,
        Some("at://did:plc:b/app.bsky.feed.post/2")
    );
}

#[test]
fn post_unparseable_created_at_is_null() {
    let bytes = cbor(json!({"text": "hi", "createdAt": "yesterday"}));
    assert_eq!(parse_post(&bytes).unwrap().created_at, None);
}

#[test]
fn post_non_map_record_is_an_error() {
    assert!(parse_post(&cbor(json!("junk"))).is_err());
    assert!(parse_post(&[0xff, 0x00]).is_err());
}

#[test]
fn post_requires_created_at() {
    let ok = cbor(json!({"createdAt": "2024-03-01T12:00:00Z"}));
    assert!(parse_post(&ok).unwrap().has_required_fields());
    let missing = cbor(json!({"text": "hi"}));
    assert!(!parse_post(&missing).unwrap().has_required_fields());
}

#[test]
fn like_or_repost_full_record() {
    let bytes = cbor(json!({
        "$type": "app.bsky.feed.like",
        "createdAt": "2024-03-01T12:00:00Z",
        "subject": {"uri": "at://did:plc:a/app.bsky.feed.post/1", "cid": "bafysubject"},
    }));
    let like = parse_like_or_repost(&bytes).unwrap();
    assert!(like.created_at.is_some());
    assert_eq!(
        like.subject_uri,
        Some("at://did:plc:a/app.bsky.feed.post/1")
    );
    assert_eq!(like.subject_cid, Some("bafysubject"));
    assert!(like.has_required_fields());
}

#[test]
fn like_or_repost_subject_wrong_type_is_null() {
    let bytes = cbor(json!({"createdAt": "2024-03-01T12:00:00Z", "subject": "did:plc:a"}));
    let like = parse_like_or_repost(&bytes).unwrap();
    assert_eq!(like.subject_uri, None);
    assert_eq!(like.subject_cid, None);
    assert!(!like.has_required_fields());
}

#[test]
fn like_or_repost_missing_cid_is_still_complete() {
    let bytes = cbor(json!({
        "createdAt": "2024-03-01T12:00:00Z",
        "subject": {"uri": "at://did:plc:a/app.bsky.feed.post/1", "cid": 5},
    }));
    let like = parse_like_or_repost(&bytes).unwrap();
    assert_eq!(like.subject_cid, None);
    assert!(like.has_required_fields());
}

#[test]
fn like_or_repost_requires_created_at() {
    let bytes = cbor(json!({"subject": {"uri": "at://did:plc:a/app.bsky.feed.post/1"}}));
    assert!(!parse_like_or_repost(&bytes).unwrap().has_required_fields());
}

#[test]
fn follow_subject_is_bare_did() {
    let bytes = cbor(json!({"createdAt": "2024-03-01T12:00:00Z", "subject": "did:plc:target"}));
    let follow = parse_follow(&bytes).unwrap();
    assert!(follow.created_at.is_some());
    assert_eq!(follow.subject_did, Some("did:plc:target"));
    assert!(follow.has_required_fields());
}

#[test]
fn follow_strongref_subject_is_null() {
    let bytes = cbor(json!({
        "createdAt": "2024-03-01T12:00:00Z",
        "subject": {"uri": "at://did:plc:a/app.bsky.actor.profile/self"},
    }));
    let follow = parse_follow(&bytes).unwrap();
    assert_eq!(follow.subject_did, None);
    assert!(!follow.has_required_fields());
}

#[test]
fn follow_requires_created_at() {
    let bytes = cbor(json!({"subject": "did:plc:target"}));
    assert!(!parse_follow(&bytes).unwrap().has_required_fields());
}

#[test]
fn like_and_follow_non_map_record_is_an_error() {
    assert!(parse_like_or_repost(&cbor(json!([1, 2]))).is_err());
    assert!(parse_follow(&cbor(json!("junk"))).is_err());
}
