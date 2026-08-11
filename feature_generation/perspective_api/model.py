"""Model for the classify_perspective_api service."""

import asyncio
import json
from typing import Literal

from googleapiclient import discovery
from googleapiclient.errors import HttpError

from feature_generation.perspective_api.schemas import PerspectiveApiLabelsModel
from lib.load_env_vars import EnvVarsContainer
from lib.timestamp_utils import get_current_timestamp

# current max of 100 QPS for the Perspective API. Also put a wait time of 1.05
# seconds to make it more unlikely that more than 2 batches go off in 1 second
# due to network latency.
DEFAULT_BATCH_SIZE = 90
DEFAULT_DELAY_SECONDS = 1.05  # enough to avoid some overlapping.


def get_google_client():
    return discovery.build(
        "commentanalyzer",
        "v1alpha1",
        developerKey=EnvVarsContainer.get_env_var("GOOGLE_API_KEY", required=True),
        discoveryServiceUrl="https://commentanalyzer.googleapis.com/$discovery/rest?version=v1alpha1",  # noqa
        static_discovery=False,
    )


attribute_to_labels_map = {
    # production-ready attributes
    "TOXICITY": {"prob": "prob_toxic", "label": "label_toxic"},
    "SEVERE_TOXICITY": {"prob": "prob_severe_toxic", "label": "label_severe_toxic"},
    "IDENTITY_ATTACK": {
        "prob": "prob_identity_attack",
        "label": "label_identity_attack",
    },
    "INSULT": {"prob": "prob_insult", "label": "label_insult"},
    "PROFANITY": {"prob": "prob_profanity", "label": "label_profanity"},
    "THREAT": {"prob": "prob_threat", "label": "label_threat"},
    # constructive attributes, from Perspective API
    "AFFINITY_EXPERIMENTAL": {"prob": "prob_affinity", "label": "label_affinity"},
    "COMPASSION_EXPERIMENTAL": {"prob": "prob_compassion", "label": "label_compassion"},
    # According to the Perspective API team, the constructiveness endpoint has
    # been deprecated in favor of the reasoning endpoint. I'll still keep the
    # same naming convention of "constructiveness", but irl it's actually
    # the "reasoning" endpoint.
    # "CONSTRUCTIVE_EXPERIMENTAL": {
    #     "prob": "prob_constructive",
    #     "label": "label_constructive",
    # },
    "CURIOSITY_EXPERIMENTAL": {"prob": "prob_curiosity", "label": "label_curiosity"},
    "NUANCE_EXPERIMENTAL": {"prob": "prob_nuance", "label": "label_nuance"},
    "PERSONAL_STORY_EXPERIMENTAL": {
        "prob": "prob_personal_story",
        "label": "label_personal_story",
    },
    "REASONING_EXPERIMENTAL": {"prob": "prob_reasoning", "label": "label_reasoning"},
    "RESPECT_EXPERIMENTAL": {"prob": "prob_respect", "label": "label_respect"},
    # persuasion attributes
    "ALIENATION_EXPERIMENTAL": {"prob": "prob_alienation", "label": "label_alienation"},
    "FEARMONGERING_EXPERIMENTAL": {
        "prob": "prob_fearmongering",
        "label": "label_fearmongering",
    },
    "GENERALIZATION_EXPERIMENTAL": {
        "prob": "prob_generalization",
        "label": "label_generalization",
    },
    "MORAL_OUTRAGE_EXPERIMENTAL": {
        "prob": "prob_moral_outrage",
        "label": "label_moral_outrage",
    },
    "SCAPEGOATING_EXPERIMENTAL": {
        "prob": "prob_scapegoating",
        "label": "label_scapegoating",
    },
    # moderation attributes
    "SEXUALLY_EXPLICIT": {
        "prob": "prob_sexually_explicit",
        "label": "label_sexually_explicit",
    },
    "FLIRTATION": {"prob": "prob_flirtation", "label": "label_flirtation"},
    "SPAM": {"prob": "prob_spam", "label": "label_spam"},
}


default_requested_attribute_keys = list(attribute_to_labels_map.keys())
default_requested_attributes = {attribute: {} for attribute in default_requested_attribute_keys}


def request_comment_analyzer(
    text: str, requested_attributes: dict = default_requested_attributes
) -> str:
    """Sends request to commentanalyzer endpoint.

    Docs at https://developers.perspectiveapi.com/s/docs-sample-requests?language=en_US

    Example request:

    analyze_request = {
    'comment': { 'text': 'friendly greetings from python' },
    'requestedAttributes': {'TOXICITY': {}}
    }

    response = client.comments().analyze(body=analyze_request).execute()
    print(json.dumps(response, indent=2))
    """  # noqa
    if not requested_attributes:
        requested_attributes = default_requested_attributes
    analyze_request = {
        "comment": {"text": text},
        "languages": ["en"],
        "requestedAttributes": requested_attributes,
    }
    print(
        f"Sending request to commentanalyzer endpoint with request={analyze_request}...",  # noqa
    )
    try:
        google_client = get_google_client()
        response = google_client.comments().analyze(body=analyze_request).execute()  # noqa
    except HttpError as e:
        print(f"Error sending request to commentanalyzer: {e}")
        response = {"error": str(e)}
    return json.dumps(response)


def classify_text_toxicity(text: str) -> dict:
    """Classify text toxicity."""
    response = request_comment_analyzer(text=text, requested_attributes={"TOXICITY": {}})
    response_obj = json.loads(response)
    toxicity_prob_score = response_obj["attributeScores"]["TOXICITY"]["summaryScore"]["value"]

    return {
        "prob_toxic": toxicity_prob_score,
        "label_toxic": 0 if toxicity_prob_score < 0.5 else 1,
    }


def process_response(response_str: str) -> dict:
    response_obj = json.loads(response_str)
    if "error" in response_obj:
        return {"error": response_obj["error"]}
    classification_probs_and_labels = {}
    for attribute, labels in attribute_to_labels_map.items():
        if attribute in response_obj["attributeScores"]:
            prob_score = (
                response_obj["attributeScores"][attribute]["summaryScore"]["value"]  # noqa
            )
            classification_probs_and_labels[labels["prob"]] = prob_score
            classification_probs_and_labels[labels["label"]] = 0 if prob_score < 0.5 else 1  # noqa
    # constructiveness == reasoning now, presumably, according to
    # the Perspective API team.
    classification_probs_and_labels["prob_constructive"] = classification_probs_and_labels[
        "prob_reasoning"
    ]
    classification_probs_and_labels["label_constructive"] = classification_probs_and_labels[
        "label_reasoning"
    ]
    return classification_probs_and_labels


def classify(text: str, attributes: dict | None = None) -> dict:
    """Classify text using Perspective API attributes."""
    requested = attributes if attributes is not None else default_requested_attributes
    response: str = request_comment_analyzer(text=text, requested_attributes=requested)
    return process_response(response)


def create_perspective_request(text: str) -> dict:
    """Build a Perspective API analyze request body for text."""
    return {
        "comment": {"text": text},
        "languages": ["en"],
        "requestedAttributes": default_requested_attributes,
    }


def _scores_from_attribute_response(response_obj: dict) -> dict:
    """Map raw attributeScores into prob_/label_ fields."""
    classification: dict = {}
    for attribute, labels in attribute_to_labels_map.items():
        if attribute not in response_obj["attributeScores"]:
            continue
        prob_score = response_obj["attributeScores"][attribute]["summaryScore"]["value"]
        classification[labels["prob"]] = prob_score
        classification[labels["label"]] = 0 if prob_score < 0.5 else 1
    classification["prob_constructive"] = classification["prob_reasoning"]
    classification["label_constructive"] = classification["label_reasoning"]
    return classification


def _append_batch_response(responses: list[dict | None], request_id, response, exception) -> None:
    """Append one batch callback result onto responses."""
    if exception is not None:
        print(f"Request {request_id} failed: {exception}")
        responses.append(None)
        return
    response_obj = json.loads(json.dumps(response))
    if "error" in response_obj:
        print(f"Request {request_id} failed: {response_obj['error']}")
        responses.append(None)
        return
    responses.append(_scores_from_attribute_response(response_obj))


async def process_perspective_batch(requests: list[dict]) -> list[dict | None]:
    """Send a Perspective batch and return per-request score dicts or None."""
    if not requests:
        return []

    google_client = get_google_client()
    batch = google_client.new_batch_http_request()
    responses: list[dict | None] = []

    def callback(request_id, response, exception):
        _append_batch_response(responses, request_id, response, exception)

    for request in requests:
        batch.add(google_client.comments().analyze(body=request), callback=callback)

    batch.execute()
    return responses


def _none_count(responses: list[dict | None]) -> int:
    return sum(1 for response in responses if response is None)


async def _retry_entire_batch(
    requests: list[dict],
    responses: list[dict | None],
    *,
    max_retries: int,
    initial_delay: float,
) -> list[dict | None]:
    current_delay = initial_delay
    attempt = 1
    while attempt < max_retries and _none_count(responses) > 0:
        fail_count = _none_count(responses)
        success_count = len(responses) - fail_count
        print(
            f"{success_count} successful, {fail_count} failed requests. "
            f"Retrying entire batch (attempt {attempt + 1}/{max_retries})..."
        )
        await asyncio.sleep(current_delay)
        responses = await process_perspective_batch(requests)
        current_delay *= 2
        attempt += 1
    return responses


async def _retry_failed_individually(
    requests: list[dict],
    responses: list[dict | None],
    *,
    max_retries: int,
    initial_delay: float,
) -> list[dict | None]:
    current_delay = initial_delay
    attempt = 1
    failed_indices = [i for i, response in enumerate(responses) if response is None]
    while failed_indices and attempt < max_retries:
        fail_count = len(failed_indices)
        success_count = len(responses) - fail_count
        print(
            f"{success_count} successful, {fail_count} failed requests. "
            f"Retrying failed requests (attempt {attempt + 1}/{max_retries})..."
        )
        await asyncio.sleep(current_delay)
        retry_requests = [requests[i] for i in failed_indices]
        retry_responses = await process_perspective_batch(retry_requests)
        for original_idx, retry_response in zip(failed_indices, retry_responses):
            if retry_response is not None:
                responses[original_idx] = retry_response
        failed_indices = [i for i, response in enumerate(responses) if response is None]
        current_delay *= 2
        attempt += 1
    return responses


async def process_perspective_batch_with_retries(
    requests: list[dict],
    max_retries: int = 4,
    initial_delay: float = 1.0,
    retry_strategy: Literal["batch", "individual"] = "individual",
) -> list[dict | None]:
    """Retry failed Perspective batch requests with exponential backoff."""
    if retry_strategy not in ("batch", "individual"):
        raise ValueError(
            f"Invalid retry_strategy: {retry_strategy}. Must be either 'batch' or 'individual'."
        )
    if not requests:
        return []

    responses = await process_perspective_batch(requests)
    if retry_strategy == "batch":
        responses = await _retry_entire_batch(
            requests, responses, max_retries=max_retries, initial_delay=initial_delay
        )
    else:
        responses = await _retry_failed_individually(
            requests, responses, max_retries=max_retries, initial_delay=initial_delay
        )

    final_failure_count = _none_count(responses)
    if final_failure_count:
        final_success_count = len(responses) - final_failure_count
        print(
            f"Final results after retries: "
            f"{final_success_count} successful, {final_failure_count} failed"
        )
    return responses


def _malformed_attribute_error(response_obj: dict) -> str | None:
    """Return an error string if attributeScores is malformed, else None."""
    error_msg: list[str] = []
    for attribute in response_obj["attributeScores"]:
        attribute_score = response_obj["attributeScores"][attribute]
        if "summaryScore" not in attribute_score:
            error_msg.append(f"Missing required field: summaryScore for {attribute}")
            continue
        if "value" not in attribute_score["summaryScore"]:
            error_msg.append(f"Missing required field: value in summaryScore for {attribute}")
    if not error_msg:
        return None
    return "; ".join(error_msg)


def _failed_label(post: dict, reason: str, label_timestamp: str) -> PerspectiveApiLabelsModel:
    return PerspectiveApiLabelsModel(
        uri=post["uri"],
        text=post["text"],
        preprocessing_timestamp=post["preprocessing_timestamp"],
        was_successfully_labeled=False,
        reason=reason,
        label_timestamp=label_timestamp,
    )


def _successful_label(
    post: dict, response_obj: dict, label_timestamp: str
) -> PerspectiveApiLabelsModel:
    probs = {
        field: float(value)
        for field, value in response_obj.items()
        if field.startswith("prob_") and isinstance(value, int | float)
    }
    return PerspectiveApiLabelsModel.model_validate(
        {
            "uri": post["uri"],
            "text": post["text"],
            "preprocessing_timestamp": post["preprocessing_timestamp"],
            "was_successfully_labeled": True,
            "label_timestamp": label_timestamp,
            **probs,
        }
    )


def _label_for_response(
    post: dict, response_obj: dict | None, label_timestamp: str
) -> PerspectiveApiLabelsModel:
    """Build one PerspectiveApiLabelsModel for a post/response pair."""
    working = response_obj
    if working is not None and "attributeScores" in working:
        malformed = _malformed_attribute_error(working)
        if malformed is not None:
            working = {"error": malformed}

    if working is None or "error" in working:
        reason = "No response from Perspective API" if working is None else str(working["error"])
        print(f"Error processing post {post['uri']} using the Perspective API: {reason}")
        return _failed_label(post, reason, label_timestamp)

    try:
        return _successful_label(post, working, label_timestamp)
    except Exception as exc:
        print(
            f"Unable to export the following record ({post}) and "
            f"label ({working}), due to error ({exc})"
        )
        return _failed_label(post, str(exc), label_timestamp)


def create_labels(posts: list[dict], responses: list[dict | None]) -> list[dict]:
    """Pair posts with Perspective responses into serialized label models."""
    if not posts:
        return []

    aligned_responses: list[dict | None] = list(responses)
    if len(aligned_responses) != len(posts):
        print(
            f"Number of responses ({len(aligned_responses)}) does not match number of "
            f"posts ({len(posts)}). Likely means that some posts failed to be "
            "labeled. Re-inserting all posts into queue..."
        )
        aligned_responses = [None] * len(posts)

    label_timestamp = get_current_timestamp()
    labels = [
        _label_for_response(post, response_obj, label_timestamp)
        for post, response_obj in zip(posts, aligned_responses)
    ]
    return [label.model_dump() for label in labels]
