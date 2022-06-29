"""move data from Cloud SQL to BigQuery for long-term storage & analysis"""

from google.cloud import bigquery


def main(event, context): # noqa
    """main function"""

    client = bigquery.Client()

    query = """
    SELECT
      failed
    FROM
      `lizaalert-bot-01.notif_archive.notif_by_user__history_20220626_100000`
    WHERE
      failed IS NOT NULL
    LIMIT
      2
    """

    query_job = client.query(query)

    for row in query_job:
        print(str(row))

    return None
