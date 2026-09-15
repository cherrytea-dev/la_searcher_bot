"""Reuse of the title recognition results instead of calling `title_recognize` again.

Title recognition is a pure function of the search title: every field the callers build from its
response (topic type, status, family name, age, locations) depends on the title text only.

So when a search title has not changed since the previous parse, the previous recognition result is
still valid — and the HTTP call to the `title_recognize` cloud function can be skipped. The same rule
is already applied in `check_first_posts_for_changes` for status checks.

Previous results are stored in the `searches` and `forum_summary_snapshot` tables, so they are
available without calling the API again.
"""


def can_reuse_recognition(
    prev_title: str | None,
    prev_topic_type_id: object | None,
    new_title: str,
) -> bool:
    """Check whether the previous recognition result for this search is still valid.

    Args:
        prev_title: title stored by the previous parse (None if the search was never parsed).
        prev_topic_type_id: recognized topic type stored by the previous parse. An empty value means
            the previous recognition did not succeed, so the API has to be called again.
        new_title: title parsed from the forum right now.
    """

    if not prev_title or prev_topic_type_id is None:
        return False

    return prev_title == new_title
