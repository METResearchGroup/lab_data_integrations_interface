SYSTEM_PROMPT = (
    "You are generating synthetic social media posts for a research dataset. "
    "Given real example posts, generate exactly one new post that matches "
    "their topic, tone, and writing style — but is not a copy or paraphrase "
    "of any single example. Posts should be under 300 characters."
)

BATCH_USER_PROMPT_TEMPLATE = (
    "Here are example posts:\n\n{examples}\n\nGenerate {n} new post(s) in the same style."
)
