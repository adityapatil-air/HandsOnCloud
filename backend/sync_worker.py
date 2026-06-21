"""
sync_worker.py — Lambda function triggered by SQS.

Each SQS message (sent by POST /api/sync) carries one sync job.
This function processes the S3 CloudTrail logs and writes job
status updates to DynamoDB so the frontend can poll progress.

Lambda handler: sync_worker.lambda_handler
SQS trigger:    cloudproof-sync-queue  (batch size = 1)
"""

import json
import os
import logging
import boto3
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYNC_JOBS_TABLE = os.getenv('SYNC_JOBS_TABLE', 'cloudproof-sync-jobs')

_dynamodb = None

def _get_table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'ap-south-1'))
    return _dynamodb.Table(SYNC_JOBS_TABLE)


def _update_job(job_id, updates: dict):
    table = _get_table()
    expr       = 'SET ' + ', '.join(f'#{k} = :{k}' for k in updates)
    attr_names  = {f'#{k}': k for k in updates}
    attr_values = {f':{k}': v for k, v in updates.items()}
    table.update_item(
        Key={'job_id': job_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )


def lambda_handler(event, context):
    """
    Entry point for SQS-triggered Lambda.
    Each SQS record contains one sync job payload.
    """
    # Import here so Lambda only loads DB/ingestion on invocation
    from credentials import decrypt_credential
    from ingestion import process_user_s3_logs

    for record in event.get('Records', []):
        body = json.loads(record['body'])

        job_id  = body['job_id']
        user_id = body['user_id']
        bucket  = body['bucket']
        prefix  = body.get('prefix', '')
        region  = body.get('region', 'us-east-1')
        ak_enc  = body.get('ak_enc', '')
        sk_enc  = body.get('sk_enc', '')

        ak = decrypt_credential(ak_enc) if ak_enc else None
        sk = decrypt_credential(sk_enc) if sk_enc else None

        _update_job(job_id, {'status': 'running', 'files_done': 0, 'files_total': 0, 'records': 0})
        logger.info(f"Starting sync job {job_id} for user {user_id}")

        try:
            files_done_count = [0]
            files_total_count = [0]

            def on_progress(event_type, value):
                if event_type == 'total':
                    files_total_count[0] = value
                    _update_job(job_id, {'files_total': value})
                elif event_type == 'batch_done':
                    files_done_count[0] += value
                    _update_job(job_id, {'files_done': files_done_count[0]})

            count = process_user_s3_logs(
                user_id=user_id,
                bucket_name=bucket,
                s3_prefix=prefix,
                aws_region=region,
                aws_access_key=ak,
                aws_secret_key=sk,
                progress_callback=on_progress,
            )

            _update_job(job_id, {'status': 'done', 'records': count})
            logger.info(f"Sync job {job_id} complete: {count} records for user {user_id}")

        except Exception as e:
            logger.error(f"Sync job {job_id} failed: {e}")
            _update_job(job_id, {'status': 'error', 'error': str(e)})
            # Re-raise so SQS can retry via DLQ if configured
            raise
