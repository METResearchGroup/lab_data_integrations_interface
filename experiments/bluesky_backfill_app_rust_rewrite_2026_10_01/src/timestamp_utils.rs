use chrono::{DateTime, Utc};

pub const CREATED_AT_FORMAT: &str = "%Y_%m_%d-%H:%M:%S";

pub fn get_current_datetime() -> DateTime<Utc> {
    Utc::now()
}

pub fn get_current_timestamp() -> String {
    get_current_datetime().format(CREATED_AT_FORMAT).to_string()
}
