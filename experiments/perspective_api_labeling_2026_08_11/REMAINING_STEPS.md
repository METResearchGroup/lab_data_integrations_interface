# Remaining steps (for AI agent)

1. Get posts locally. Should result in 2 .parquet post files. Git add commit and push these .parquet files.
2. Run labeling for one post day at a time. Do all its labeling and then consolidate its labels. After completing consolidating, git add commit and push the labels .parquet files.
3. Once all labeling is done, do analysis (see below)

## Analysis

Put the Python scripts for each step (1 script per step) in analysis/{daily,hourly}_averages.py. Put outputs in analysis/outputs/{daily,hourly}/{assets}.

1. What is the average of each Perspective API label per day? Report as a two-row table. Each row is a date and each column is a float of the average of the measure. Put this in a per_day_average.json and report in RESULTS.md.
2. What is the per-hour average of each attribute? Put this in a per_hour_average.json. One key per attribute,  and the value should be date + hour (e.g,. "2026-08-09:01" or "2026-08-09:03"). Base this off the created_at timestamp of the original post. May need to join the labels against the original posts data file. Put this in a per_hour_average.json. Then for each, create a line graph average, with the X axis being the date+hour (e.g,. "2026-08-09:01"), sorted earliest to latest left to right, and the value is the average. Put this in a {attribute}_per_hour_average.png (e.g., "constructiveness_per_hour_average.png").
