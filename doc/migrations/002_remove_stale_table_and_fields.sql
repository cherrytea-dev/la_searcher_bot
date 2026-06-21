ALTER TABLE notif_mailings DROP COLUMN source_script;
ALTER TABLE notif_mailings DROP COLUMN topic_id;
ALTER TABLE notif_mailings DROP COLUMN mailing_type;
DROP TABLE IF EXISTS notif_mailing_status;
