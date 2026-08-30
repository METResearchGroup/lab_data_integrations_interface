# Flush vs. drain

Both sound like "empty the thing." They are not interchangeable. Use them as
defined here in code, logs, and PRs.

## flush — write buffered data out to persistent storage

One bounded write of in-memory data to somewhere it survives the process, fired
by a threshold (count, size, age) or by shutdown. The buffer is empty after.
What makes it a flush is the direction, volatile → durable.

## drain — keep pulling from a source until it is empty

A loop, not a write: read a batch, handle it, read again, stop when the source
comes back empty or a deadline passes. No buffer.

## Choosing the word
Lost on process death → flush. Survives it → drain. "Flush the queue" and
"drain the buffer" are both wrong; rename before merging. `clear()` is the
in-memory half of a flush and does no I/O.
