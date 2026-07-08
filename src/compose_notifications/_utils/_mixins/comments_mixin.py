"""Mixin: Comments operations."""

from typing import Any

import sqlalchemy

from _dependencies.common.db_client import DBClientMixinBase


class CommentsMixin(DBClientMixinBase):
    """DB operations on the comments table."""

    def get_unprocessed_comments_for_search(self, forum_search_num: int) -> list[Any]:
        """Get all unprocessed comments for a search with full column set."""
        with self.connect() as conn:
            query = sqlalchemy.text("""
                SELECT comment_url, comment_text, comment_author_nickname,
                       comment_author_link, search_forum_num, comment_num, comment_global_num
                FROM comments
                WHERE notification_sent IS NULL
                  AND search_forum_num = :forum_search_num;
            """)
            return conn.execute(query, dict(forum_search_num=forum_search_num)).fetchall()

    def get_unprocessed_inforg_comments_for_search(self, forum_search_num: int) -> list[Any]:
        """Get unprocessed inforg comments for a search with full column set."""
        with self.connect() as conn:
            query = sqlalchemy.text("""
                SELECT comment_url, comment_text, comment_author_nickname,
                       comment_author_link, search_forum_num, comment_num, comment_global_num
                FROM comments
                WHERE notif_sent_inforg IS NULL
                  AND LOWER(LEFT(comment_author_nickname, 6)) = 'инфорг'
                  AND comment_author_nickname != 'Инфорг кинологов'
                  AND search_forum_num = :forum_search_num;
            """)
            return conn.execute(query, dict(forum_search_num=forum_search_num)).fetchall()

    def mark_comments_processed(self, search_forum_num: int) -> None:
        """Mark all unprocessed comments as sent for a search."""
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE comments
                    SET notification_sent='y'
                    WHERE search_forum_num=:forum_search_num
                      AND notification_sent IS NULL;
                """),
                dict(forum_search_num=search_forum_num),
            )

    def mark_events_comments_processed(self, search_forum_num: int) -> None:
        """Mark DСЛ/в работе comments as processed for a search."""
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE comments
                    SET notification_sent='y'
                    WHERE search_forum_num=:forum_search_num
                      AND notification_sent IS NULL
                      AND (comment_text ILIKE '%ДСЛ%' OR comment_text ILIKE '%в работе%');
                """),
                dict(forum_search_num=search_forum_num),
            )

    def mark_comments_processed_by_change_type(self, forum_search_num: int, change_type: int) -> None:
        """Mark comments as processed based on change type (3=comment, 4=inforg comment)."""
        with self.connect() as conn:
            if change_type == 3:  # ChangeType.topic_comment_new
                conn.execute(
                    sqlalchemy.text("""
                        UPDATE comments SET notification_sent = 'y'
                        WHERE search_forum_num=:forum_search_num;
                    """),
                    dict(forum_search_num=forum_search_num),
                )
            elif change_type == 4:  # ChangeType.topic_inforg_comment_new
                conn.execute(
                    sqlalchemy.text("""
                        UPDATE comments SET notif_sent_inforg = 'y'
                        WHERE search_forum_num=:forum_search_num;
                    """),
                    dict(forum_search_num=forum_search_num),
                )
            else:
                # Fallback: mark all
                conn.execute(
                    sqlalchemy.text("""
                        UPDATE comments SET notification_sent = 'y'
                        WHERE notification_sent is Null OR notification_sent = 's';
                    """),
                )
                conn.execute(
                    sqlalchemy.text("""
                        UPDATE comments SET notif_sent_inforg = 'y'
                        WHERE notif_sent_inforg is Null;
                    """),
                )

    def mark_all_comments_processed_fallback(self) -> None:
        """Fallback: mark ALL comments as processed (used in except block)."""
        with self.connect() as conn:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE comments SET notification_sent = 'y'
                    WHERE notification_sent is Null OR notification_sent = 's';
                """)
            )
            conn.execute(
                sqlalchemy.text("""
                    UPDATE comments SET notif_sent_inforg = 'y'
                    WHERE notif_sent_inforg is Null;
                """)
            )
