def preprocess_records():
    # loads from data_platform/data/bluesky/preprocessed/{latest timestamp}/{metadata.json, *.parquet}
    # writes to data_platform/data/bluesky/preprocessed/{timestamp}/{metadata.json, *.parquet}
    print("preprocess_records: preprocessing Bluesky records")
