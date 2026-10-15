use chrono::{DateTime, Utc};
use serde::de::IgnoredAny;
use serde::{Deserialize, Deserializer};

pub type DecodeError = serde_ipld_dagcbor::DecodeError<std::convert::Infallible>;

#[derive(Debug, PartialEq)]
pub struct Post<'a> {
    pub created_at: Option<DateTime<Utc>>,
    pub text: Option<&'a str>,
    pub langs: Option<Vec<&'a str>>,
    pub reply_root_uri: Option<&'a str>,
    pub reply_parent_uri: Option<&'a str>,
    pub embed_type: Option<&'a str>,
}

#[derive(Debug, PartialEq)]
pub struct LikeOrRepost<'a> {
    pub created_at: Option<DateTime<Utc>>,
    pub subject_uri: Option<&'a str>,
    pub subject_cid: Option<&'a str>,
}

#[derive(Debug, PartialEq)]
pub struct Follow<'a> {
    pub created_at: Option<DateTime<Utc>>,
    pub subject_did: Option<&'a str>,
}

// REQUIRED_KEYS: uri, did and ingested_at are always set in backfill, so only these can be null.
impl Post<'_> {
    pub fn has_required_fields(&self) -> bool {
        self.created_at.is_some()
    }
}

impl LikeOrRepost<'_> {
    pub fn has_required_fields(&self) -> bool {
        self.created_at.is_some() && self.subject_uri.is_some()
    }
}

impl Follow<'_> {
    pub fn has_required_fields(&self) -> bool {
        self.created_at.is_some() && self.subject_did.is_some()
    }
}

#[derive(Deserialize)]
#[serde(untagged)]
enum Lenient<T> {
    Valid(T),
    Junk(IgnoredAny),
}

pub fn lenient<'de, D, T>(deserializer: D) -> Result<Option<T>, D::Error>
where
    D: Deserializer<'de>,
    T: Deserialize<'de>,
{
    match Lenient::deserialize(deserializer)? {
        Lenient::Valid(value) => Ok(Some(value)),
        Lenient::Junk(_) => Ok(None),
    }
}

pub fn parse_created_at(value: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|dt| dt.with_timezone(&Utc))
}

#[derive(Deserialize)]
struct RawPost<'a> {
    #[serde(default, borrow, deserialize_with = "lenient")]
    text: Option<&'a str>,
    #[serde(default, borrow, deserialize_with = "lenient")]
    langs: Option<Vec<Lenient<&'a str>>>,
    #[serde(rename = "createdAt", default, borrow, deserialize_with = "lenient")]
    created_at: Option<&'a str>,
    #[serde(default, borrow, deserialize_with = "lenient")]
    reply: Option<RawReply<'a>>,
    #[serde(default, borrow, deserialize_with = "lenient")]
    embed: Option<RawEmbed<'a>>,
}

#[derive(Deserialize)]
struct RawReply<'a> {
    #[serde(default, borrow, deserialize_with = "lenient")]
    root: Option<RawStrongRef<'a>>,
    #[serde(default, borrow, deserialize_with = "lenient")]
    parent: Option<RawStrongRef<'a>>,
}

#[derive(Deserialize)]
struct RawStrongRef<'a> {
    #[serde(default, borrow, deserialize_with = "lenient")]
    uri: Option<&'a str>,
    #[serde(default, borrow, deserialize_with = "lenient")]
    cid: Option<&'a str>,
}

#[derive(Deserialize)]
struct RawEmbed<'a> {
    #[serde(rename = "$type", default, borrow, deserialize_with = "lenient")]
    embed_type: Option<&'a str>,
}

pub fn parse_post(record: &[u8]) -> Result<Post<'_>, DecodeError> {
    let raw: RawPost = serde_ipld_dagcbor::from_slice(record)?;
    let reply = raw.reply.as_ref();
    Ok(Post {
        created_at: raw.created_at.and_then(parse_created_at),
        text: raw.text,
        langs: raw.langs.map(|langs| {
            langs
                .into_iter()
                .filter_map(|lang| match lang {
                    Lenient::Valid(lang) => Some(lang),
                    Lenient::Junk(_) => None,
                })
                .collect()
        }),
        reply_root_uri: reply.and_then(|r| r.root.as_ref()).and_then(|r| r.uri),
        reply_parent_uri: reply.and_then(|r| r.parent.as_ref()).and_then(|r| r.uri),
        embed_type: raw.embed.and_then(|e| e.embed_type),
    })
}

#[derive(Deserialize)]
struct RawLikeOrRepost<'a> {
    #[serde(rename = "createdAt", default, borrow, deserialize_with = "lenient")]
    created_at: Option<&'a str>,
    #[serde(default, borrow, deserialize_with = "lenient")]
    subject: Option<RawStrongRef<'a>>,
}

pub fn parse_like_or_repost(record: &[u8]) -> Result<LikeOrRepost<'_>, DecodeError> {
    let raw: RawLikeOrRepost = serde_ipld_dagcbor::from_slice(record)?;
    let subject = raw.subject.as_ref();
    Ok(LikeOrRepost {
        created_at: raw.created_at.and_then(parse_created_at),
        subject_uri: subject.and_then(|s| s.uri),
        subject_cid: subject.and_then(|s| s.cid),
    })
}

// `subject` is a bare DID string here, not a strongref like likes and reposts.
#[derive(Deserialize)]
struct RawFollow<'a> {
    #[serde(rename = "createdAt", default, borrow, deserialize_with = "lenient")]
    created_at: Option<&'a str>,
    #[serde(default, borrow, deserialize_with = "lenient")]
    subject: Option<&'a str>,
}

pub fn parse_follow(record: &[u8]) -> Result<Follow<'_>, DecodeError> {
    let raw: RawFollow = serde_ipld_dagcbor::from_slice(record)?;
    Ok(Follow {
        created_at: raw.created_at.and_then(parse_created_at),
        subject_did: raw.subject,
    })
}
