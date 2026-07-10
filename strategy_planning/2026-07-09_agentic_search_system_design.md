# System Design: Agentic Search

Text-to-SQL.

Likely steps are:

- Expand the query functionality to take on more generic queries (let's discuss later what this means)
- Add V1 text-to-SQL functionality, very naive (prompting an LLM to query, we'll pass into the LLM prompt the list of tables and their fields). We'll turn this into an experiment in experiments/ to have a proof of concept.
- We'll make this more robust (add validation, avoid prompt injection, make sure queries don't give results that are too large, etc). We can do more experiments for this step as well.
- Then we can put into production (still vague as to what that means).

## High-level design

```mermaid
flowchart LR
    U["User query:<br/>'I want all posts liked by Stanley<br/>in the past 2 weeks'"]
    FE["Frontend checks,<br/>e.g., rate limits"]
    GW["API Gateway<br/>(auth, rate limits,<br/>middleware, etc)"]
    BE["Backend: Clean up user request /<br/>prevent prompt injection / jailbreak"]
    CACHE["Caching layer"]
    ROUTER{"Is this a user request<br/>that is valid? router"}

    INV["Invalid"]
    INV1["Invalid because we don't<br/>have that metadata/user"]
    INV2["Invalid because we<br/>lack the kind of data"]
    INV3["Invalid because the<br/>user request is nonsense"]
    DEF["Default response"]

    LLM["Ask an LLM to<br/>create the SQL query"]
    VAL_SQL["Validate / post-process<br/>the SQL query"]
    EXPLAIN["Run 'EXPLAIN ANALYZE'<br/>on the query"]
    EXPENSIVE["If query is too expensive, return a<br/>default response and tell them to contact<br/>the team. Can also give feedback on how<br/>to change/constrain the prompt."]
    SQL_CACHE["Check cache for SQL queries<br/>(higher priority for large queries;<br/>for smaller queries, cost of keeping<br/>in cache may not be worth it)"]
    CACHE_HIT["Return the result directly"]
    DB["On cache miss (or skip):<br/>DB / data pool executes the query"]
    VAL_RES["Validate / post-process<br/>the results"]

    U --> FE --> GW --> BE --> CACHE
    CACHE -->|"On cache hit,<br/>return to user"| U
    CACHE --> ROUTER

    ROUTER --> INV
    INV --> INV1 & INV2 & INV3 --> DEF

    ROUTER --> LLM --> VAL_SQL
    VAL_SQL -->|"Retry X times"| LLM
    VAL_SQL --> EXPLAIN
    EXPLAIN --> EXPENSIVE
    EXPLAIN --> SQL_CACHE
    SQL_CACHE --> CACHE_HIT
    SQL_CACHE --> DB --> VAL_RES
    VAL_RES --> U
    VAL_RES --> CACHE
```

## Implementation details

### Prompting

Possible draft prompt for "ask an LLM to create the query":

```markdown
{SYSTEM_PROMPT}

{cleaned up version of the user's prompt}.  

This is a query that a user has for our DB.

{tables + columns from Glue}

Here are some example requests from users and the correct SQL queries for those requests:

"I want all posts by Stanley in the past month" -> "SELECT * FROM posts WHERE handle LIKE "Stanley" AND created_at > {past month}"

{example requests + SQL queries}

Given that we have these columns and tables, generate an Athena SQL query for this user's request.

{cleaned up version of the user's prompt}
```

We'll need to do some experiments and have eval datasets to see if we're generating the right prompts.

### Caching