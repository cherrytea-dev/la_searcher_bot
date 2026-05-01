--drop table phpbb_posts_history ;

CREATE TABLE phpbb_posts_history (
    history_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    operation_type ENUM('INSERT', 'UPDATE', 'DELETE') NOT NULL,
    operation_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- дублируем все поля из phpbb_posts (приведите типы в соответствие с оригиналом)
    post_id MEDIUMINT(8) UNSIGNED NOT NULL,
    topic_id MEDIUMINT(8) UNSIGNED NOT NULL,
    forum_id MEDIUMINT(8) UNSIGNED NOT NULL,
    poster_id MEDIUMINT(8) UNSIGNED NOT NULL,
    post_time INT(11) UNSIGNED NOT NULL,
    post_edit_time INT(11) UNSIGNED NOT NULL DEFAULT '0',
--    post_edit_count SMALLINT(4) UNSIGNED NOT NULL DEFAULT '0',
    post_edit_user MEDIUMINT(8) UNSIGNED NOT NULL DEFAULT '0',
    post_subject VARCHAR(255) NOT NULL DEFAULT '',
    post_text MEDIUMTEXT NOT NULL,
    PRIMARY KEY (history_id),
    INDEX idx_post_id (post_id),
    INDEX idx_operation_time (operation_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;




CREATE TRIGGER posts_after_insert
AFTER INSERT ON phpbb_posts
FOR EACH ROW
INSERT INTO phpbb_posts_history (
    operation_type, post_id, topic_id, forum_id, poster_id,
    post_time, post_edit_time,  post_edit_user,
    post_subject, post_text
) VALUES (
    'INSERT', NEW.post_id, NEW.topic_id, NEW.forum_id, NEW.poster_id,
    NEW.post_time, NEW.post_edit_time,  NEW.post_edit_user,
    NEW.post_subject, NEW.post_text
);


CREATE TRIGGER posts_after_update
AFTER UPDATE ON phpbb_posts
FOR EACH ROW
INSERT INTO phpbb_posts_history (
    operation_type, post_id, topic_id, forum_id, poster_id,
    post_time, post_edit_time, post_edit_user,
    post_subject, post_text
) VALUES (
    'UPDATE', NEW.post_id, NEW.topic_id, NEW.forum_id, NEW.poster_id,
    NEW.post_time, NEW.post_edit_time, NEW.post_edit_user,
    NEW.post_subject, NEW.post_text
);


CREATE TRIGGER posts_before_delete
BEFORE DELETE ON phpbb_posts
FOR EACH ROW
INSERT INTO phpbb_posts_history (
    operation_type, post_id, topic_id, forum_id, poster_id,
    post_time, post_edit_time,  post_edit_user,
    post_subject, post_text
) VALUES (
    'DELETE', OLD.post_id, OLD.topic_id, OLD.forum_id, OLD.poster_id,
    OLD.post_time, OLD.post_edit_time,  OLD.post_edit_user,
    OLD.post_subject, OLD.post_text
);
