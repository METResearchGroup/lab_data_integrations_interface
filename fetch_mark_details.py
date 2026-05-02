import os

from atproto import Client
from dotenv import load_dotenv

load_dotenv()

BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE")
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")

MARK_HANDLE = "markptorres.bsky.social"


def show_name(profile):
    print(f"Name: {profile.display_name}\n")


def show_handle(profile):
    print(f"Handle: {profile.handle}\n")


def show_num_followers(profile):
    print(f"Followers: {profile.followers_count}\n")

def show_num_following(profile):
    print(f"Following: {profile.follows_count}\n")


def show_last_10_posts(feed):
    print("Last 10 Posts/Reposts:")
    for i, item in enumerate(feed.feed):
        post = item.post
        print(f"{i+1}: {post.record.text[:80]!r}")
    print()


def show_last_10_followers(followers):
    print("Last 10 Followers:")
    for i, f in enumerate(followers.followers):
        print(f"{i+1}: {f.handle} ({f.display_name})")
    print()


def show_last_10_following(follows):
    print("Last 10 Following:")
    for i, f in enumerate(follows.follows):
        print(f"{i+1}: {f.handle} ({f.display_name})")
    print()


def main():
    client = Client()
    client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)

    profile = client.app.bsky.actor.get_profile({"actor": MARK_HANDLE})
    feed = client.app.bsky.feed.get_author_feed({"actor": MARK_HANDLE, "limit": 10})
    followers = client.app.bsky.graph.get_followers({"actor": MARK_HANDLE, "limit": 10})
    follows = client.app.bsky.graph.get_follows({"actor": MARK_HANDLE, "limit": 10})

    show_name(profile)
    show_handle(profile)
    show_num_followers(profile)
    show_num_following(profile)
    show_last_10_posts(feed)
    show_last_10_followers(followers)
    show_last_10_following(follows)


if __name__ == "__main__":
    main()
