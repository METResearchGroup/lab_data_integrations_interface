# System Design: Agentic Search

Text-to-SQL.

Likely steps are:

- Expand the query functionality to take on more generic queries (let's discuss later what this means)
- Add V1 text-to-SQL functionality, very naive (prompting an LLM to query, we'll pass into the LLM prompt the list of tables and their fields). We'll turn this into an experiment in experiments/ to have a proof of concept.
- We'll make this more robust (add validation, avoid prompt injection, make sure queries don't give results that are too large, etc). We can do more experiments for this step as well.
- Then we can put into production (still vague as to what that means).
