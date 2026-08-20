<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Combining backfill and Jetstream (2026-08-18)](#combining-backfill-and-jetstream-2026-08-18)
  - [The split](#the-split)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Combining backfill and Jetstream (2026-08-18)

## The split

2026-08-01 is the cutoff. A row whose `created_at` falls on or after 2026-08-01 comes from
Jetstream; anything earlier comes from the backfill.