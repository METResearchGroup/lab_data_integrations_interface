# loads preprocessed posts

from data_platform.generate_features.is_news_or_opinion.generate_feature import generate_feature as is_news_or_opinion

feature_name_to_fn_map = {
    "is_news_or_opinion": is_news_or_opinion
}

# load posts to generate features for. This is whatever is the latest preprocessed batch.
# generate features. Only do so for posts that don't have labels.

def _generate_features():
    for i, (feature_name, fn) in enumerate(feature_name_to_fn_map.items()):
        pass

def generate_features():
    # load posts
    # filter out posts whose features already exist.
    # generate features.
