ALTER TABLE notif_mailings 
        DROP COLUMN source_script, 
        DROP COLUMN topic_id,
        DROP COLUMN mailing_type;
DROP TABLE IF EXISTS notif_mailing_status;
