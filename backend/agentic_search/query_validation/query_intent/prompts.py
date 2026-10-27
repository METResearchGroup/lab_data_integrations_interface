"""Prompt for turning a question into a QueryIntent."""

EXTRACT_USER_QUERY_INTENT_PROMPT = """\
Map the user's question onto our Bluesky tables.

Today is {today}.

Tables, their columns, and the dates they cover:
{catalog}

Set is_nonsense only when the input is not a coherent question about Bluesky
data. A coherent question about records we do not hold is not nonsense.

Otherwise: pick the one record type it asks about, list every column it asks
for, and resolve its dates against today. Leave a date null only when the
question does not bound that side.

keywords are the post-text terms to filter on. Leave keywords empty when the
question does not ask to filter by what a post says. Asking for the text
column is not a keyword filter. Copy the words the question names. Do not
stem them, expand them to synonyms, or rank results. A phrase the user wants
matched as a phrase is one keyword, not one keyword per word. The query is
refused past {max_keywords} terms or {max_keyword_length} characters in one
term, so leave an over-cap list intact rather than dropping or splitting it.

match is "any" when one term is enough, and "all" when every term must
appear. A single term is "any".

use_whole_word is true for ordinary words and phrases, so "cat" does not match
"category" and "climate change" matches that phrase. Set use_whole_word false
when a word boundary would not match the term:
- hashtags and mentions, because "#" and "@" are not word characters
- Chinese, Japanese, or Korean text, because the boundary is ASCII and does
  not fall between those characters
A mention is the handle as written in the post, such as "@alice.bsky.social",
not the author's DID.

Do not put matched_keywords in columns. The query adds that column itself.

Report what the question asks for, not the closest thing the tables hold.
Never swap in a similar record type or column for an absent one, and do not
add columns the question does not ask for. When the question names no
columns, use "uri". When it is a keyword question and names no columns, use
"text".

Worked examples, for a catalog holding posts (uri, text, langs), likes
(uri, subject_uri) and follows (uri, subject_did), where today is 2026-06-10:

  "zxcvb qwerty"
    is_nonsense=true record_type=null columns=[] keywords=[] match=any
    use_whole_word=true start=null end=null
  "list every block someone made"
    is_nonsense=false record_type=null columns=[] keywords=[] match=any
    use_whole_word=true start=null end=null
  "likes from the last three days"
    is_nonsense=false record_type=likes columns=["uri"] keywords=[] match=any
    use_whole_word=true start=2026-06-07 end=2026-06-10
  "follows with their vanity handles"
    is_nonsense=false record_type=follows columns=["subject_did","vanity handles"]
    keywords=[] match=any use_whole_word=true start=null end=null
  "likes from February 2024"
    is_nonsense=false record_type=likes columns=["uri"] keywords=[] match=any
    use_whole_word=true start=2024-02-01 end=2024-02-29
  "posts from June 1 through June 3 2026 that say climate"
    is_nonsense=false record_type=posts columns=["text"] keywords=["climate"]
    match=any use_whole_word=true start=2026-06-01 end=2026-06-03
  "posts from the last three days that mention trump or biden"
    is_nonsense=false record_type=posts columns=["text"]
    keywords=["trump","biden"] match=any use_whole_word=true
    start=2026-06-07 end=2026-06-10
  "posts from May 2026 that mention both climate and policy"
    is_nonsense=false record_type=posts columns=["text"]
    keywords=["climate","policy"] match=all use_whole_word=true
    start=2026-05-01 end=2026-05-31
  "posts from June 1 through June 3 2026 with the phrase climate change"
    is_nonsense=false record_type=posts columns=["text"]
    keywords=["climate change"] match=any use_whole_word=true
    start=2026-06-01 end=2026-06-03
  "posts from June 1 through June 3 2026 tagged #climate"
    is_nonsense=false record_type=posts columns=["text"] keywords=["#climate"]
    match=any use_whole_word=false start=2026-06-01 end=2026-06-03
  "posts from June 1 through June 3 2026 that mention 气候"
    is_nonsense=false record_type=posts columns=["text"] keywords=["气候"]
    match=any use_whole_word=false start=2026-06-01 end=2026-06-03
  "posts from the last three days, with text and language"
    is_nonsense=false record_type=posts columns=["text","langs"] keywords=[]
    match=any use_whole_word=true start=2026-06-07 end=2026-06-10
"""
