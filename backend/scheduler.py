"""
CloudProof Auto-Sync Scheduler
On Lambda: triggered by EventBridge cron(0 2 * * ? *)
Locally:   python scheduler.py
"""
import logging
import sys
from datetime import datetime
from database import execute_query
from ingestion import process_user_s3_logs
from credentials import decrypt_credential

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def sync_all_users():
    """Fetch all users with credentials and sync their CloudTrail logs."""
    logger.info(f"=== Auto-sync started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    try:
        users = execute_query(
            """SELECT id, username, email, s3_bucket, s3_prefix, aws_region,
                      aws_access_key_encrypted, aws_secret_key_encrypted
               FROM users
               WHERE s3_bucket IS NOT NULL
               AND aws_access_key_encrypted IS NOT NULL""",
            fetch=True
        )
    except Exception as e:
        logger.error(f"Failed to fetch users: {e}")
        return

    if not users:
        logger.info("No users with credentials found. Skipping.")
        return

    logger.info(f"Found {len(users)} users to sync.")

    success = 0
    failed  = 0

    for user in users:
        username = user.get('username') or f"user_{user['id']}"
        try:
            # Decrypt stored credentials
            ak = decrypt_credential(user['aws_access_key_encrypted'])
            sk = decrypt_credential(user['aws_secret_key_encrypted'])

            logger.info(f"Syncing @{username} (id={user['id']}) from s3://{user['s3_bucket']}")

            count = process_user_s3_logs(
                user_id       = user['id'],
                bucket_name   = user['s3_bucket'],
                s3_prefix     = user.get('s3_prefix') or '',
                aws_region    = user.get('aws_region') or 'us-east-1',
                aws_access_key= ak,
                aws_secret_key= sk,
            )

            logger.info(f"@{username}: {count} new records processed.")
            success += 1

            # Update last_auto_synced_at
            execute_query(
                "UPDATE users SET last_auto_synced_at = %s WHERE id = %s",
                (datetime.now(), user['id'])
            )

        except Exception as e:
            logger.error(f"@{username} sync failed: {e}")
            failed += 1
            continue

    logger.info(f"=== Auto-sync complete: {success} succeeded, {failed} failed ===")


# ── Lambda entry point (EventBridge trigger) ─────────────────────────────────
def lambda_handler(event, context):
    """Called by EventBridge rule: cron(0 2 * * ? *)"""
    sync_all_users()


# ── Local entry point ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    import schedule
    import time

    logger.info('CloudProof scheduler started — runs daily at 02:00')
    sync_all_users()  # run once on startup
    schedule.every().day.at('02:00').do(sync_all_users)
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        sys.exit(0)
