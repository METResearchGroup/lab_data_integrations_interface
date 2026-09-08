# Data request details from Nick

Original source document [is here](https://docs.google.com/document/d/1PSDTEPw9beKZHUmC1-4UaAmpGONB0SF-ekfbGSYS3y0/edit?tab=t.pli4dze1w1no). In this doc is a distilled version.

For each person we want, over the past 12 months:

1. Account creation date
2. All original posts
3. All posts they liked
4. All posts they reposted
5. All posts they quoted (what they said in the quote + the post that was quoted)
6. All posts they replied to (what they said in the reply + the post that was replied to)
7. All posts they saved
8. A list of all their followers at the end of the 12 months within all collected profiles
9. A list of all their followees at the end of the 12 months within all collected profiles
10. Latest count of total followers
11. Latest count of total followees
12. All follow actions in the 12 months
13. All unfollow actions in the 12 months (is that possible?)
14. Their current bio.
15. Their handle
16. Their display name

For each post:

1. Time stamp
2. Post type: is it an original post or an item in a thread?
3. Does it include media (video, image)?
4. Language field
5. Number of likes
6. Number of replies
7. Number of reposts
8. Number of quotes
9. Number of saves

For each quote/repost/reply/like/save

1. Full data from original post
2. Author of original post
3. Timestamp.

For each follow action:

1. ID of profile that was followed
2. Timestamp

Intentionally out of scope:

1. Post deletions
2. Unfollows

## Initial scoping

The hardest part is hydrating every single post liked or engaged with, for every single person throughout that period. From my experiments with getting all likes/posts/reposts/comments from a random subset of 1,000 followers of AOC, that was something like average total of ~1,400 for 6 months of engagement (obviously very skewed by some large accounts):

949 likes
88 original posts
173 reposts
179 replies

Unsure how representative this is as compared to your dataset, but also likely that there are some larger nodes that are being captured. We'll deduplicate and do other tricks to try to optimize, but also your ask is for 12 months instead of 6 months which'll double the average. If we assume that we need to hydrate, say, 2,800 posts per user, across 8,000 users, that's ~22.5M posts.

The docs seem to suggest that the AppView for app.bsky.feed.getPosts doesn't have a stated rate limit, but is "generous", whatever that might mean. We can try at 10 QPS first. Looks like it's max 25 URIs/request. Conservatively, that might mean 1 day at the very fastest. However, from my past experience, they can throttle you pretty hard.

Basically, there's three parts to split this work into:

Run getProfiles for all the users. Should take ~30 minutes.
Run getRepo  for all the users. Should take ~12 hours.
Run getPosts for posts. Some optimizations include filtering down which posts to get data for, but assuming the worst case estimates here and assuming the 3,000 requests/5 minutes rate limit.

Steps 1 and 2 are the quickest and get you the majority of data.
