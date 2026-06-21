from flask import Flask, jsonify, request
from flask_cors import CORS
from database import execute_query
from datetime import datetime, timedelta
import logging
import os
import re
import uuid
import random
import secrets
import json as _json
import boto3
from werkzeug.security import generate_password_hash, check_password_hash
from ingestion import process_local_cloudtrail_logs, process_s3_cloudtrail_logs, process_user_s3_logs, store_activities
from scoring import calculate_score, DAILY_SCORE_CAP, SERVICE_DAILY_CAP, ACTION_DAILY_CAP
from config import get_credibility, CREDIBILITY_TIERS
from auth import (
    hash_password, verify_password, generate_token, require_auth,
    generate_verification_token, verify_email_token,
    generate_reset_token, verify_reset_token, consume_reset_token,
)
from credentials import encrypt_credential, decrypt_credential
from oauth import generate_state, verify_state, github_auth_url, github_get_user, google_auth_url, google_get_user
from emailer import send_verification_email, send_reset_email

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

SYNC_JOBS_TABLE = os.getenv('SYNC_JOBS_TABLE', 'cloudproof-sync-jobs')
SYNC_QUEUE_URL  = os.getenv('SYNC_QUEUE_URL', '')

_dynamodb = None

def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'ap-south-1'))
    return _dynamodb

def _get_job(job_id):
    try:
        table = _get_dynamodb().Table(SYNC_JOBS_TABLE)
        resp  = table.get_item(Key={'job_id': job_id})
        return resp.get('Item')
    except Exception as e:
        logger.error(f'DynamoDB get_job error: {e}')
        return None

def _put_job(job_id, item):
    try:
        table = _get_dynamodb().Table(SYNC_JOBS_TABLE)
        table.put_item(Item={'job_id': job_id, **item})
    except Exception as e:
        logger.error(f'DynamoDB put_job error: {e}')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app,
     origins=[FRONTEND_URL, 'https://handsoncloud.in', 'http://localhost:3000'],
     supports_credentials=True,
     allow_headers=['Content-Type', 'Authorization'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
)

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        execute_query("SELECT 1", fetch=True)
        return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 503

@app.route('/api/users', methods=['POST'])
def create_user():
    try:
        data = request.json
        
        if not data or not all(k in data for k in ['name', 'email', 'role_arn']):
            return jsonify({'error': 'Missing required fields: name, email, role_arn'}), 400
        
        # Check if email already exists
        existing = execute_query(
            "SELECT id FROM users WHERE email = %s",
            (data['email'],),
            fetch=True
        )
        
        if existing:
            return jsonify({'error': 'User with this email already exists'}), 409
        
        execute_query(
    "INSERT INTO users (name, email, role_arn) VALUES (%s, %s, %s)",
    (data['name'], data['email'], data['role_arn'])
    )
        
        logger.info(f"User created: {data['email']}")
        return jsonify({'message': 'User created successfully'}), 201
        
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({'error': 'Failed to create user'}), 500

@app.route('/api/users/<int:user_id>/activity', methods=['GET'])
def get_user_activity(user_id):
    try:
        # Verify user exists
        user = execute_query(
            "SELECT id FROM users WHERE id = %s",
            (user_id,),
            fetch=True
        )
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        days = int(request.args.get('days', 365))
        if days < 1 or days > 730:
            return jsonify({'error': 'Days must be between 1 and 730'}), 400
        
        start_date = datetime.now().date() - timedelta(days=days)
        
        daily_scores = execute_query(
            "SELECT date, total_score FROM daily_scores WHERE user_id = %s AND date >= %s ORDER BY date",
            (user_id, start_date),
            fetch=True
        )
        
        service_breakdown = execute_query(
            "SELECT service, SUM(score) as total FROM activity_logs WHERE user_id = %s AND date >= %s GROUP BY service ORDER BY total DESC",
            (user_id, start_date),
            fetch=True
        )
        
        recent_actions = execute_query(
            "SELECT date, service, action, score FROM activity_logs WHERE user_id = %s ORDER BY date DESC, id DESC LIMIT 20",
            (user_id,),
            fetch=True
        )
        
        heatmap = {row['date'].isoformat(): int(row['total_score']) for row in daily_scores}
        services = {row['service']: int(row['total']) for row in service_breakdown}
        
        return jsonify({
            'heatmap': heatmap,
            'services': services,
            'recent_actions': [
                {
                    'date': str(row['date']),
                    'service': row['service'],
                    'action': row['action'],
                    'score': int(row['score'])
                } for row in recent_actions
            ],
            'total_score': sum(services.values())
        }), 200
        
    except ValueError:
        return jsonify({'error': 'Invalid days parameter'}), 400
    except Exception as e:
        logger.error(f"Error fetching user activity: {str(e)}")
        return jsonify({'error': 'Failed to fetch user activity'}), 500


@app.route('/api/users/<int:user_id>/dashboard', methods=['GET'])
def get_user_dashboard(user_id):
    try:
        user = execute_query(
            "SELECT id, name, email FROM users WHERE id = %s",
            (user_id,),
            fetch=True
        )
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        days = int(request.args.get('days', 30))
        start_date = datetime.now().date() - timedelta(days=days)
        
        daily_usage = execute_query(
            """
            SELECT 
                date,
                service,
                action,
                score,
                COALESCE(timestamp, created_at) as timestamp
            FROM activity_logs 
            WHERE user_id = %s AND date >= %s 
            ORDER BY date DESC, COALESCE(timestamp, created_at) DESC
            """,
            (user_id, start_date),
            fetch=True
        )
        
        dashboard_data = {}
        for row in daily_usage:
            date_str = row['date'].isoformat()
            if date_str not in dashboard_data:
                dashboard_data[date_str] = {
                    'date': date_str,
                    'services': {},
                    'total_actions': 0,
                    'total_score': 0
                }
            
            service = row['service']
            if service not in dashboard_data[date_str]['services']:
                dashboard_data[date_str]['services'][service] = {
                    'count': 0,
                    'actions': [],
                    'total_score': 0
                }
            
            dashboard_data[date_str]['services'][service]['count'] += 1
            dashboard_data[date_str]['services'][service]['total_score'] += row['score']
            timestamp_val = row['timestamp']
            if isinstance(timestamp_val, str):
                timestamp_str = timestamp_val
            elif timestamp_val:
                timestamp_str = timestamp_val.isoformat()
            else:
                timestamp_str = None
            dashboard_data[date_str]['services'][service]['actions'].append({
                'action': row['action'],
                'score': row['score'],
                'timestamp': timestamp_str
            })
            dashboard_data[date_str]['total_actions'] += 1
            dashboard_data[date_str]['total_score'] += row['score']
        
        result = sorted(dashboard_data.values(), key=lambda x: x['date'], reverse=True)
        
        return jsonify({
            'user': {
                'id': user[0]['id'],
                'name': user[0]['name'],
                'email': user[0]['email']
            },
            'dashboard': result
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching dashboard: {str(e)}")
        return jsonify({'error': 'Failed to fetch dashboard'}), 500

@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    try:
        user = execute_query(
            "SELECT id, name, email, created_at FROM users WHERE id = %s",
            (user_id,),
            fetch=True
        )
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user_data = dict(user[0])
        user_data['created_at'] = user_data['created_at'].isoformat()
        
        return jsonify(user_data), 200
        
    except Exception as e:
        logger.error(f"Error fetching user: {str(e)}")
        return jsonify({'error': 'Failed to fetch user'}), 500

@app.route('/api/users', methods=['GET'])
def list_users():
    try:
        users = execute_query(
            "SELECT id, name, email, created_at FROM users ORDER BY created_at DESC",
            fetch=True
        )
        
        return jsonify([
            {
                'id': user['id'],
                'name': user['name'],
                'email': user['email'],
                'created_at': user['created_at'].isoformat()
            } for user in users
        ]), 200
        
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        return jsonify({'error': 'Failed to list users'}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        user = execute_query(
            "SELECT id FROM users WHERE id = %s",
            (user_id,),
            fetch=True
        )
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        execute_query("DELETE FROM users WHERE id = %s", (user_id,))
        
        logger.info(f"User deleted: {user_id}")
        return jsonify({'message': 'User deleted successfully'}), 200
        
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        return jsonify({'error': 'Failed to delete user'}), 500


@app.route('/api/debug/daily-scores', methods=['GET'])
def debug_daily_scores():
    try:
        rows = execute_query(
            "SELECT user_id, date, total_score FROM daily_scores ORDER BY date DESC, user_id ASC",
            fetch=True,
        )
        return jsonify(rows), 200
    except Exception as e:
        logger.error(f"Error fetching daily_scores debug data: {str(e)}")
        return jsonify({'error': 'Failed to fetch daily scores'}), 500


@app.route('/api/process-sample-logs', methods=['POST'])
def process_sample_logs():
    """
    Manually trigger processing of local CloudTrail-style logs
    from backend/sample_logs using process_local_cloudtrail_logs().
    """
    try:
        processed_count = process_local_cloudtrail_logs()
        return (
            jsonify(
                {
                    'message': 'Processed local sample CloudTrail logs',
                    'records_processed': processed_count,
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"Error processing sample logs: {str(e)}")
        return jsonify({'error': 'Failed to process sample logs'}), 500


@app.route('/api/process-s3-logs', methods=['POST'])
def process_s3_logs():
    """
    Manually trigger processing of CloudTrail-style logs from the
    fixed S3 bucket using process_s3_cloudtrail_logs().
    """
    try:
        processed_count = process_s3_cloudtrail_logs("cloudproof-test-logs")
        return (
            jsonify(
                {
                    "message": "Processed S3 CloudTrail logs",
                    "records_processed": processed_count,
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"Error processing S3 logs: {str(e)}")
        return jsonify({"error": "Failed to process S3 logs"}), 500

@app.route('/api/users/<int:user_id>/resources', methods=['GET'])
def get_user_resources(user_id):
    try:
        user = execute_query(
            "SELECT id FROM users WHERE id = %s",
            (user_id,),
            fetch=True
        )
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        resources = execute_query(
            """
            SELECT 
                resource_type,
                resource_id,
                parent_resource_id,
                state,
                metadata,
                last_updated
            FROM resource_state 
            WHERE user_id = %s 
            ORDER BY last_updated DESC
            """,
            (user_id,),
            fetch=True
        )
        
        result = []
        for row in resources:
            timestamp_val = row['last_updated']
            if isinstance(timestamp_val, str):
                timestamp_str = timestamp_val
            elif timestamp_val:
                timestamp_str = timestamp_val.isoformat()
            else:
                timestamp_str = None
                
            result.append({
                'resource_type': row['resource_type'],
                'resource_id': row['resource_id'],
                'parent_resource_id': row['parent_resource_id'],
                'state': row['state'],
                'metadata': row['metadata'],
                'last_updated': timestamp_str
            })
        
        return jsonify({
            'resources': result
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching resources: {str(e)}")
        return jsonify({'error': 'Failed to fetch resources'}), 500

# ─── Public Profile Endpoints ────────────────────────────────────────────────

@app.route('/api/register', methods=['POST'])
def register_user():
    """Create a new public profile. Stores S3 bucket config for log ingestion."""
    data = request.json
    required = ['username', 'name', 'email', 's3_bucket', 'sync_pin']
    if not data or not all(k in data for k in required):
        return jsonify({'error': f'Missing required fields: {", ".join(required)}'}), 400

    username = data['username'].strip().lower()
    if not re.match(r'^[a-z0-9_-]+$', username):
        return jsonify({'error': 'Username can only contain lowercase letters, numbers, hyphens, and underscores'}), 400
    if len(username) < 3 or len(username) > 30:
        return jsonify({'error': 'Username must be between 3 and 30 characters'}), 400

    sync_pin = data['sync_pin']
    if len(sync_pin) < 4:
        return jsonify({'error': 'Sync password must be at least 4 characters'}), 400

    existing_username = execute_query(
        "SELECT id FROM users WHERE username = %s", (username,), fetch=True
    )
    if existing_username:
        return jsonify({'error': 'Username already taken'}), 409

    existing_email = execute_query(
        "SELECT id FROM users WHERE email = %s", (data['email'],), fetch=True
    )
    if existing_email:
        return jsonify({'error': 'Email already registered'}), 409

    s3_bucket = data['s3_bucket'].strip()
    s3_prefix = data.get('s3_prefix', '').strip()
    aws_region = data.get('aws_region', 'us-east-1').strip() or 'us-east-1'
    pin_hash = generate_password_hash(sync_pin)

    execute_query(
        "INSERT INTO users (username, name, email, s3_bucket, s3_prefix, aws_region, sync_pin_hash) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (username, data['name'].strip(), data['email'].strip(), s3_bucket, s3_prefix, aws_region, pin_hash)
    )

    logger.info(f"New profile created: {username} → s3://{s3_bucket}/{s3_prefix}")
    return jsonify({'message': 'Profile created successfully', 'username': username}), 201


@app.route('/api/profile/<username>', methods=['GET'])
def get_profile(username):
    """Return the full public profile for a username — used by the profile page."""
    user = execute_query(
        "SELECT id, username, name, email, s3_bucket, aws_region, created_at FROM users WHERE username = %s",
        (username.lower(),),
        fetch=True
    )
    if not user:
        return jsonify({'error': 'Profile not found'}), 404

    user_row = user[0]
    user_id = user_row['id']

    days = int(request.args.get('days', 365))
    if days < 1 or days > 730:
        days = 365
    start_date = datetime.now().date() - timedelta(days=days)

    daily_scores = execute_query(
        "SELECT date, total_score FROM daily_scores WHERE user_id = %s AND date >= %s ORDER BY date",
        (user_id, start_date),
        fetch=True
    )
    service_breakdown = execute_query(
        "SELECT service, SUM(score) as total FROM activity_logs WHERE user_id = %s AND date >= %s GROUP BY service ORDER BY total DESC",
        (user_id, start_date),
        fetch=True
    )
    recent_actions = execute_query(
        "SELECT date, service, action, score FROM activity_logs WHERE user_id = %s ORDER BY date DESC, id DESC LIMIT 20",
        (user_id,),
        fetch=True
    )

    heatmap = {row['date'].isoformat() if hasattr(row['date'], 'isoformat') else str(row['date']): int(row['total_score']) for row in daily_scores}
    services = {row['service']: int(row['total']) for row in service_breakdown}
    total_score = sum(services.values())

    # Compute streaks server-side
    sorted_dates = sorted(heatmap.keys())
    current_streak = 0
    max_streak = 0
    if sorted_dates:
        temp = 1
        for i in range(1, len(sorted_dates)):
            prev = datetime.strptime(sorted_dates[i - 1], '%Y-%m-%d').date()
            curr = datetime.strptime(sorted_dates[i], '%Y-%m-%d').date()
            if (curr - prev).days == 1:
                temp += 1
                max_streak = max(max_streak, temp)
            else:
                temp = 1
        max_streak = max(max_streak, 1)

        # Current streak: walk back from most recent active day
        current_streak = 1
        for i in range(len(sorted_dates) - 2, -1, -1):
            prev = datetime.strptime(sorted_dates[i], '%Y-%m-%d').date()
            nxt = datetime.strptime(sorted_dates[i + 1], '%Y-%m-%d').date()
            if (nxt - prev).days == 1:
                current_streak += 1
            else:
                break

    created_at = user_row['created_at']
    if hasattr(created_at, 'isoformat'):
        created_at = created_at.isoformat()
    else:
        created_at = str(created_at)

    return jsonify({
        'user': {
            'username': user_row['username'],
            'name': user_row['name'],
            'created_at': created_at,
        },
        'heatmap': heatmap,
        'services': services,
        'recent_actions': [
            {
                'date': str(row['date']),
                'service': row['service'],
                'action': row['action'],
                'score': int(row['score']),
            } for row in recent_actions
        ],
        'total_score': total_score,
        'streaks': {'current': current_streak, 'longest': max_streak},
        'credibility': get_credibility(total_score),
        'tiers': CREDIBILITY_TIERS,
    }), 200


@app.route('/api/profile/<username>/sync', methods=['POST'])
def sync_profile(username):
    """Pull latest CloudTrail logs from the user's S3 bucket and update their scores.
    Requires the sync_pin set at registration to prevent others from triggering syncs."""
    data = request.json or {}
    sync_pin = data.get('sync_pin', '')

    user = execute_query(
        "SELECT id, s3_bucket, s3_prefix, aws_region, sync_pin_hash FROM users WHERE username = %s",
        (username.lower(),),
        fetch=True
    )
    if not user:
        return jsonify({'error': 'Profile not found'}), 404

    row = user[0]

    # Verify ownership via sync PIN
    pin_hash = row['sync_pin_hash']
    if not pin_hash or not sync_pin or not check_password_hash(pin_hash, sync_pin):
        return jsonify({'error': 'Invalid sync password'}), 403

    if not row['s3_bucket']:
        return jsonify({'error': 'No S3 bucket configured for this profile'}), 400

    try:
        count = process_user_s3_logs(
            user_id=row['id'],
            bucket_name=row['s3_bucket'],
            s3_prefix=row['s3_prefix'] or '',
            aws_region=row['aws_region'] or 'us-east-1',
        )
        logger.info(f"Sync complete for {username}: {count} records processed")
        return jsonify({'message': 'Sync complete', 'records_processed': count}), 200
    except Exception as e:
        logger.error(f"Sync failed for {username}: {str(e)}")
        return jsonify({'error': f'Sync failed: {str(e)}'}), 500


@app.route('/api/profile/<username>/dashboard', methods=['GET'])
def get_profile_dashboard(username):
    """Dashboard view for a profile — daily breakdown by service and action."""
    user = execute_query(
        "SELECT id FROM users WHERE username = %s", (username.lower(),), fetch=True
    )
    if not user:
        return jsonify({'error': 'Profile not found'}), 404

    user_id = user[0]['id']
    days = int(request.args.get('days', 30))
    if days < 1 or days > 365:
        days = 30
    start_date = datetime.now().date() - timedelta(days=days)

    daily_usage = execute_query(
        """
        SELECT date, service, action, score,
               COALESCE(timestamp, created_at) as timestamp
        FROM activity_logs
        WHERE user_id = %s AND date >= %s
        ORDER BY date DESC, COALESCE(timestamp, created_at) DESC
        """,
        (user_id, start_date),
        fetch=True
    )

    dashboard_data = {}
    for row in daily_usage:
        date_str = row['date'].isoformat() if hasattr(row['date'], 'isoformat') else str(row['date'])
        if date_str not in dashboard_data:
            dashboard_data[date_str] = {'date': date_str, 'services': {}, 'total_actions': 0, 'total_score': 0}

        service = row['service']
        if service not in dashboard_data[date_str]['services']:
            dashboard_data[date_str]['services'][service] = {'count': 0, 'actions': [], 'total_score': 0}

        ts = row['timestamp']
        ts_str = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts) if ts else None

        dashboard_data[date_str]['services'][service]['count'] += 1
        dashboard_data[date_str]['services'][service]['total_score'] += row['score']
        dashboard_data[date_str]['services'][service]['actions'].append({
            'action': row['action'], 'score': row['score'], 'timestamp': ts_str
        })
        dashboard_data[date_str]['total_actions'] += 1
        dashboard_data[date_str]['total_score'] += row['score']

    return jsonify({
        'dashboard': sorted(dashboard_data.values(), key=lambda x: x['date'], reverse=True)
    }), 200


@app.route('/api/profile/<username>/resources', methods=['GET'])
def get_profile_resources(username):
    """Resource inventory for a profile."""
    user = execute_query(
        "SELECT id FROM users WHERE username = %s", (username.lower(),), fetch=True
    )
    if not user:
        return jsonify({'error': 'Profile not found'}), 404

    user_id = user[0]['id']
    resources = execute_query(
        """
        SELECT resource_type, resource_id, parent_resource_id, state, metadata, last_updated
        FROM resource_state
        WHERE user_id = %s
        ORDER BY last_updated DESC
        """,
        (user_id,),
        fetch=True
    )

    result = []
    for row in resources:
        ts = row['last_updated']
        result.append({
            'resource_type': row['resource_type'],
            'resource_id': row['resource_id'],
            'parent_resource_id': row['parent_resource_id'],
            'state': row['state'],
            'metadata': row['metadata'],
            'last_updated': ts.isoformat() if hasattr(ts, 'isoformat') else str(ts) if ts else None,
        })

    return jsonify({'resources': result}), 200


@app.route('/api/profile/<username>/test-sync', methods=['POST'])
def test_sync_profile(username):
    """DEV ONLY — generate random CloudTrail-like events and process them for this profile.
    Requires sync_pin to prevent accidental or unauthorised use."""
    if os.environ.get('FLASK_ENV') == 'production':
        return jsonify({'error': 'Not available in production'}), 403

    data     = request.json or {}
    sync_pin = data.get('sync_pin', '')

    user = execute_query(
        "SELECT id, sync_pin_hash FROM users WHERE username = %s",
        (username.lower(),), fetch=True
    )
    if not user:
        return jsonify({'error': 'Profile not found'}), 404

    row = user[0]
    if not sync_pin or not check_password_hash(row['sync_pin_hash'], sync_pin):
        return jsonify({'error': 'Invalid sync password'}), 403

    activities = _generate_test_activities(row['id'])
    if activities:
        store_activities(activities)

    return jsonify({
        'message': f'Generated and processed {len(activities)} test activity records',
        'count': len(activities),
    }), 200


def _generate_test_activities(user_id):
    """Return a list of fake scored activity dicts spread across the last 90 days."""
    SAMPLE_EVENTS = [
        ('ec2', 'RunInstances'), ('ec2', 'TerminateInstances'), ('ec2', 'CreateSecurityGroup'),
        ('ec2', 'AuthorizeSecurityGroupIngress'), ('ec2', 'CreateKeyPair'), ('ec2', 'AllocateAddress'),
        ('s3', 'CreateBucket'), ('s3', 'PutBucketPolicy'), ('s3', 'PutObject'), ('s3', 'DeleteObject'),
        ('iam', 'CreateRole'), ('iam', 'AttachRolePolicy'), ('iam', 'CreateUser'), ('iam', 'CreatePolicy'),
        ('lambda', 'CreateFunction'), ('lambda', 'UpdateFunctionCode'), ('lambda', 'PublishVersion'),
        ('rds', 'CreateDBInstance'), ('rds', 'CreateDBSnapshot'), ('rds', 'ModifyDBInstance'),
        ('eks', 'CreateCluster'), ('eks', 'CreateNodegroup'),
        ('ecs', 'CreateCluster'), ('ecs', 'RegisterTaskDefinition'), ('ecs', 'RunTask'),
        ('cloudformation', 'CreateStack'), ('cloudformation', 'UpdateStack'), ('cloudformation', 'DeleteStack'),
        ('dynamodb', 'CreateTable'), ('dynamodb', 'PutItem'), ('dynamodb', 'UpdateTable'),
        ('route53', 'CreateHostedZone'), ('route53', 'ChangeResourceRecordSets'),
    ]

    today = datetime.now().date()
    # Pick ~55 random days out of the last 90 to simulate realistic usage
    active_offsets = sorted(random.sample(range(90), min(55, 90)))

    activities = []
    daily_totals         = {}
    daily_service_scores = {}
    daily_action_scores  = {}

    for offset in active_offsets:
        date_key   = today - timedelta(days=offset)
        num_events = random.randint(3, 14)
        sample     = random.choices(SAMPLE_EVENTS, k=num_events)

        for event_source, event_name in sample:
            service      = event_source.upper()
            action       = event_name
            score        = calculate_score(service, action)
            if score <= 0:
                continue

            service_key = f"{date_key}_{service}"
            action_key  = f"{date_key}_{service}_{action}"

            daily_totals.setdefault(date_key, 0)
            daily_service_scores.setdefault(service_key, 0)
            daily_action_scores.setdefault(action_key, 0)

            if daily_totals[date_key]         >= DAILY_SCORE_CAP:    continue
            if daily_service_scores[service_key] >= SERVICE_DAILY_CAP: continue
            if daily_action_scores[action_key]   >= ACTION_DAILY_CAP:  continue

            activities.append({
                'user_id': user_id,
                'date':    date_key,
                'service': service,
                'action':  action,
                'score':   score,
                # Each test run gets unique event IDs so it doesn't de-dup with previous runs
                'event_id': str(uuid.uuid4()),
            })

            daily_totals[date_key]            += score
            daily_service_scores[service_key] += score
            daily_action_scores[action_key]   += score

    return activities


# ═══════════════════════════════════════════════════════════════════════════════
# JWT AUTH ROUTES  (/api/auth/*)
# These add proper login/signup on top of the existing sync-pin system.
# Existing routes (/api/register, /api/profile/*) are NOT changed.
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/auth/preflight', methods=['POST'])
def auth_preflight():
    """
    Step 1 of signup: Validate username/email availability WITHOUT creating the account.
    Account is only created after AWS credentials are verified in /api/credentials/register.
    """
    try:
        data = request.json or {}
        missing = [f for f in ['username', 'email', 'password'] if not data.get(f)]
        if missing:
            return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400

        username = data['username'].strip().lower()
        email    = data['email'].strip().lower()
        password = data['password']

        if not re.match(r'^[a-z0-9_-]{3,30}$', username):
            return jsonify({'error': 'Username: 3–30 chars, lowercase letters/numbers/hyphens/underscores.'}), 400
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters.'}), 400
        if execute_query("SELECT id FROM users WHERE email = %s", (email,), fetch=True):
            return jsonify({'error': 'Email already registered.'}), 409
        if execute_query("SELECT id FROM users WHERE username = %s", (username,), fetch=True):
            return jsonify({'error': 'Username already taken.'}), 409

        # All good — tell frontend to proceed to AWS credentials step
        return jsonify({'success': True, 'message': 'Username and email are available.'}), 200
    except Exception as e:
        logger.error(f"auth_preflight error: {e}")
        return jsonify({'error': 'Validation failed.'}), 500


@app.route('/api/auth/signup', methods=['POST'])
def auth_signup():
    """
    Final signup step: called AFTER AWS credentials are verified.
    Creates the account only when we know the AWS Account ID is unique.
    Expects: username, name, email, password, access_key, secret_key, region
    """
    try:
        data = request.json or {}
        missing = [f for f in ['username', 'name', 'email', 'password', 'access_key', 'secret_key'] if not data.get(f)]
        if missing:
            return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400

        username   = data['username'].strip().lower()
        name       = data['name'].strip()
        email      = data['email'].strip().lower()
        password   = data['password']
        access_key = data['access_key'].strip()
        secret_key = data['secret_key'].strip()
        region     = data.get('region', 'us-east-1').strip()

        if not re.match(r'^[a-z0-9_-]{3,30}$', username):
            return jsonify({'error': 'Username: 3–30 chars, lowercase letters/numbers/hyphens/underscores.'}), 400
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters.'}), 400
        if execute_query("SELECT id FROM users WHERE email = %s", (email,), fetch=True):
            return jsonify({'error': 'Email already registered.'}), 409
        if execute_query("SELECT id FROM users WHERE username = %s", (username,), fetch=True):
            return jsonify({'error': 'Username already taken.'}), 409

        # Verify AWS credentials and get Account ID
        try:
            sts = boto3.client('sts', aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region)
            identity = sts.get_caller_identity()
            aws_account_id = identity['Account']
            aws_user_arn   = identity['Arn']
        except Exception as aws_err:
            return jsonify({'error': f'Invalid AWS credentials: {aws_err}'}), 400

        # Check AWS Account ID uniqueness BEFORE creating account
        existing = execute_query(
            "SELECT username FROM users WHERE aws_account_id = %s",
            (aws_account_id,), fetch=True
        )
        if existing:
            return jsonify({
                'error': f'This AWS account is already linked to @{existing[0]["username"]}. '
                         f'Each AWS account can only have one CloudProof profile.'
            }), 409

        # All checks passed — NOW create the account
        from credentials import encrypt_credential
        pwd_hash = hash_password(password)
        execute_query(
            "INSERT INTO users (username, name, email, password_hash, aws_account_id, aws_user_arn, "
            "aws_access_key_encrypted, aws_secret_key_encrypted, aws_region) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (username, name, email, pwd_hash, aws_account_id, aws_user_arn,
             encrypt_credential(access_key), encrypt_credential(secret_key), region)
        )

        user = execute_query("SELECT id, username, name, email FROM users WHERE email = %s", (email,), fetch=True)
        u     = user[0]
        token = generate_token(u['id'])
        logger.info(f"New account created: {username} ({email}) -> AWS account {aws_account_id}")

        ver_token = generate_verification_token(u['id'])
        send_verification_email(email, ver_token)

        return jsonify({
            'success': True,
            'message': 'Account created successfully.',
            'token': token,
            'user': {
                'id':             u['id'],
                'username':       u['username'],
                'name':           u['name'],
                'email':          u['email'],
                'email_verified': False,
                'has_bucket':     False,
            },
        }), 201
    except Exception as e:
        logger.error(f"auth_signup error: {e}")
        return jsonify({'error': 'Failed to create account.'}), 500


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """JWT login with email + password. Returns signed token."""
    try:
        data = request.json or {}
        email    = (data.get('email')    or '').strip().lower()
        password =  data.get('password') or ''
        if not email or not password:
            return jsonify({'error': 'Email and password are required.'}), 400

        user = execute_query(
            "SELECT id, username, name, email, password_hash, s3_bucket, aws_region FROM users WHERE email = %s",
            (email,), fetch=True
        )
        if not user or not user[0].get('password_hash'):
            return jsonify({'error': 'Invalid email or password.'}), 401
        if not verify_password(user[0]['password_hash'], password):
            return jsonify({'error': 'Invalid email or password.'}), 401

        u     = user[0]
        token = generate_token(u['id'])
        logger.info(f"JWT login: {email}")
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id':         u['id'],
                'username':   u.get('username'),
                'name':       u.get('name'),
                'email':      u['email'],
                'has_bucket': bool(u.get('s3_bucket')),
            },
        }), 200
    except Exception as e:
        logger.error(f"auth_login error: {e}")
        return jsonify({'error': 'Login failed.'}), 500


@app.route('/api/auth/me', methods=['GET'])
@require_auth
def auth_me(user_id):
    """Return current authenticated user's info."""
    try:
        user = execute_query(
            "SELECT id, username, name, email, s3_bucket, aws_region, created_at FROM users WHERE id = %s",
            (user_id,), fetch=True
        )
        if not user:
            return jsonify({'error': 'User not found.'}), 404
        u  = user[0]
        ca = u.get('created_at')
        return jsonify({
            'success': True,
            'user': {
                'id':         u['id'],
                'username':   u.get('username'),
                'name':       u.get('name'),
                'email':      u['email'],
                'has_bucket': bool(u.get('s3_bucket')),
                'aws_region': u.get('aws_region', 'us-east-1'),
                'created_at': ca.isoformat() if hasattr(ca, 'isoformat') else str(ca),
            },
        }), 200
    except Exception as e:
        logger.error(f"auth_me error: {e}")
        return jsonify({'error': 'Failed to fetch user.'}), 500


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """Stateless logout — client discards the token."""
    return jsonify({'success': True, 'message': 'Logged out.'}), 200


# ── AWS Credential & Bucket Setup ─────────────────────────────────────────────

@app.route('/api/credentials', methods=['POST'])
@require_auth
def save_credentials(user_id):
    """
    Store the user's AWS access key + secret (encrypted).
    Called from the Setup wizard after login.
    """
    try:
        data = request.json or {}
        access_key = (data.get('access_key') or '').strip()
        secret_key = (data.get('secret_key') or '').strip()
        region     = (data.get('region')     or 'us-east-1').strip()

        if not access_key or not secret_key:
            return jsonify({'error': 'Both access_key and secret_key are required.'}), 400

        # Step 1: Call STS GetCallerIdentity to validate credentials and get Account ID
        try:
            sts = boto3.client(
                'sts',
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
            identity = sts.get_caller_identity()
            aws_account_id = identity['Account']  # e.g. "751285160227"
            aws_user_arn   = identity['Arn']       # e.g. "arn:aws:iam::751285160227:user/john"
        except Exception as aws_err:
            return jsonify({'error': f'AWS credentials are invalid: {aws_err}'}), 400

        # Step 2: Check if this AWS Account ID is already linked to another CloudProof account
        existing = execute_query(
            "SELECT username FROM users WHERE aws_account_id = %s AND id != %s",
            (aws_account_id, user_id),
            fetch=True
        )
        if existing:
            return jsonify({
                'error': f'This AWS account ({aws_account_id}) is already linked to @{existing[0]["username"]}. '
                         f'Each AWS account can only have one CloudProof profile.'
            }), 409

        # Step 3: Check if current user already has a DIFFERENT AWS account linked
        current = execute_query(
            "SELECT aws_account_id FROM users WHERE id = %s",
            (user_id,),
            fetch=True
        )
        if current and current[0]['aws_account_id'] and current[0]['aws_account_id'] != aws_account_id:
            return jsonify({
                'error': 'Your profile is already linked to a different AWS account. '
                         'Each CloudProof profile can only be linked to one AWS account.'
            }), 409

        # Step 4: Save credentials + account identity
        execute_query(
            "UPDATE users SET aws_access_key_encrypted = %s, aws_secret_key_encrypted = %s, "
            "aws_region = %s, aws_account_id = %s, aws_user_arn = %s WHERE id = %s",
            (encrypt_credential(access_key), encrypt_credential(secret_key), region, aws_account_id, aws_user_arn, user_id)
        )
        logger.info(f"Credentials saved for user {user_id}")
        return jsonify({'success': True, 'message': 'AWS credentials saved.'}), 200
    except Exception as e:
        logger.error(f"save_credentials error: {e}")
        return jsonify({'error': 'Failed to save credentials.'}), 500


@app.route('/api/buckets', methods=['GET'])
@require_auth
def list_buckets(user_id):
    """List S3 buckets visible to the user's stored AWS credentials."""
    try:
        row = execute_query(
            "SELECT aws_access_key_encrypted, aws_secret_key_encrypted, aws_region FROM users WHERE id = %s",
            (user_id,), fetch=True
        )
        if not row or not row[0].get('aws_access_key_encrypted'):
            return jsonify({'error': 'No AWS credentials configured. Save credentials first.'}), 400

        r  = row[0]
        ak = decrypt_credential(r['aws_access_key_encrypted'])
        sk = decrypt_credential(r['aws_secret_key_encrypted'])

        s3       = boto3.client('s3', aws_access_key_id=ak, aws_secret_access_key=sk, region_name=r.get('aws_region', 'us-east-1'))
        response = s3.list_buckets()
        buckets  = [b['Name'] for b in response.get('Buckets', [])]
        return jsonify({'success': True, 'buckets': buckets}), 200
    except Exception as e:
        logger.error(f"list_buckets error: {e}")
        return jsonify({'error': f'Failed to list buckets: {str(e)}'}), 500


@app.route('/api/buckets/select', methods=['POST'])
@require_auth
def select_bucket(user_id):
    """Save the chosen S3 bucket (and optional prefix) to the user's profile."""
    try:
        data      = request.json or {}
        bucket    = (data.get('bucket')    or '').strip()
        s3_prefix = (data.get('s3_prefix') or '').strip()
        if not bucket:
            return jsonify({'error': 'bucket is required.'}), 400

        execute_query(
            "UPDATE users SET s3_bucket = %s, s3_prefix = %s WHERE id = %s",
            (bucket, s3_prefix, user_id)
        )
        logger.info(f"User {user_id} selected bucket: {bucket}")
        return jsonify({'success': True, 'message': 'Bucket saved.', 'bucket': bucket}), 200
    except Exception as e:
        logger.error(f"select_bucket error: {e}")
        return jsonify({'error': 'Failed to save bucket.'}), 500


@app.route('/api/sync', methods=['POST'])
@require_auth
def sync_logs(user_id):
    """Enqueue an async log sync via SQS. Returns job_id immediately; poll /api/sync/status/<job_id>."""
    try:
        row = execute_query(
            "SELECT s3_bucket, s3_prefix, aws_region, aws_access_key_encrypted, aws_secret_key_encrypted FROM users WHERE id = %s",
            (user_id,), fetch=True
        )
        if not row or not row[0].get('s3_bucket'):
            return jsonify({'error': 'No S3 bucket configured. Complete setup first.'}), 400

        if not SYNC_QUEUE_URL:
            return jsonify({'error': 'Sync queue not configured (SYNC_QUEUE_URL missing).'}), 500

        r      = row[0]
        job_id = secrets.token_hex(8)

        # Write initial job state to DynamoDB
        _put_job(job_id, {
            'status':      'queued',
            'user_id':     user_id,
            'files_done':  0,
            'files_total': 0,
            'records':     0,
            'error':       None,
        })

        # Push message to SQS — sync_worker Lambda will pick it up
        sqs = boto3.client('sqs', region_name=os.getenv('AWS_REGION', 'ap-south-1'))
        sqs.send_message(
            QueueUrl=SYNC_QUEUE_URL,
            MessageBody=_json.dumps({
                'job_id':    job_id,
                'user_id':   user_id,
                'bucket':    r['s3_bucket'],
                'prefix':    r.get('s3_prefix') or '',
                'region':    r.get('aws_region') or 'us-east-1',
                'ak_enc':    r.get('aws_access_key_encrypted') or '',
                'sk_enc':    r.get('aws_secret_key_encrypted') or '',
            }),
        )
        logger.info(f"Sync job {job_id} queued for user {user_id}")
        return jsonify({'job_id': job_id}), 202
    except Exception as e:
        logger.error(f"sync_logs error: {e}")
        return jsonify({'error': f'Failed to start sync: {str(e)}'}), 500


@app.route('/api/sync/status/<job_id>', methods=['GET'])
@require_auth
def sync_status(user_id, job_id):
    """Poll sync job status from DynamoDB."""
    job = _get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify({
        'status':      job.get('status'),
        'files_done':  int(job.get('files_done',  0)),
        'files_total': int(job.get('files_total', 0)),
        'records':     int(job.get('records',     0)),
        'error':       job.get('error'),
    }), 200


# ── OAuth helpers ─────────────────────────────────────────────────────────────

def _unique_username(base: str) -> str:
    """Return base username if free, else append incrementing numbers."""
    base = re.sub(r'[^a-z0-9_-]', '', base.lower())[:25] or 'user'
    candidate = base
    counter = 2
    while execute_query("SELECT id FROM users WHERE username = %s", (candidate,), fetch=True):
        candidate = f"{base}{counter}"
        counter += 1
    return candidate


def _oauth_upsert_user(provider: str, info: dict) -> dict:
    """
    Find or create a user from OAuth profile data.
    Priority: oauth_id match → email match → create new.
    Returns the user row dict.
    """
    oauth_id = info['oauth_id']
    email    = (info.get('email') or '').strip().lower() or None

    # 1. Find by provider + oauth_id
    existing = execute_query(
        "SELECT id, username, name, email, s3_bucket FROM users WHERE oauth_provider = %s AND oauth_id = %s",
        (provider, oauth_id), fetch=True
    )
    if existing:
        return existing[0]

    # 2. Find by email — link the OAuth provider to the existing account
    if email:
        by_email = execute_query(
            "SELECT id, username, name, email, s3_bucket FROM users WHERE email = %s",
            (email,), fetch=True
        )
        if by_email:
            execute_query(
                "UPDATE users SET oauth_provider = %s, oauth_id = %s, email_verified = 1 WHERE id = %s",
                (provider, oauth_id, by_email[0]['id'])
            )
            return by_email[0]

    # 3. Create new user
    username = _unique_username(info.get('username_hint', 'user'))
    name     = (info.get('name') or username).strip()
    verified = 1 if info.get('email_verified') else 0

    execute_query(
        "INSERT INTO users (username, name, email, oauth_provider, oauth_id, email_verified) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (username, name, email, provider, oauth_id, verified)
    )
    user = execute_query(
        "SELECT id, username, name, email, s3_bucket FROM users WHERE username = %s",
        (username,), fetch=True
    )
    logger.info(f"New OAuth user created: {username} via {provider}")
    return user[0]


def _oauth_error_redirect(msg: str):
    from flask import redirect as flask_redirect
    import urllib.parse
    return flask_redirect(f"{FRONTEND_URL}/login?error={urllib.parse.quote(msg)}")


# ═══════════════════════════════════════════════════════════════════════════════
# SOCIAL AUTH ROUTES  (/api/auth/github/*  /api/auth/google/*)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/auth/github')
def auth_github():
    """Kick off GitHub OAuth flow."""
    from flask import redirect as flask_redirect
    state = generate_state('github')
    return flask_redirect(github_auth_url(state))


@app.route('/api/auth/github/callback')
def auth_github_callback():
    """GitHub redirects here after user authorises."""
    from flask import redirect as flask_redirect
    import urllib.parse

    error = request.args.get('error')
    if error:
        return _oauth_error_redirect(request.args.get('error_description', 'GitHub auth failed.'))

    state = request.args.get('state', '')
    if not verify_state(state, 'github'):
        return _oauth_error_redirect('Invalid or expired OAuth state. Please try again.')

    code = request.args.get('code', '')
    try:
        info  = github_get_user(code)
        user  = _oauth_upsert_user('github', info)
        token = generate_token(user['id'])
        params = urllib.parse.urlencode({
            'token':    token,
            'username': user['username'],
            'has_bucket': '1' if user.get('s3_bucket') else '0',
        })
        return flask_redirect(f"{FRONTEND_URL}/auth/callback?{params}")
    except Exception as e:
        logger.error(f"GitHub callback error: {e}")
        return _oauth_error_redirect('GitHub sign-in failed. Please try again.')


@app.route('/api/auth/google')
def auth_google():
    """Kick off Google OAuth flow."""
    from flask import redirect as flask_redirect
    state = generate_state('google')
    return flask_redirect(google_auth_url(state))


@app.route('/api/auth/google/callback')
def auth_google_callback():
    """Google redirects here after user authorises."""
    from flask import redirect as flask_redirect
    import urllib.parse

    error = request.args.get('error')
    if error:
        return _oauth_error_redirect('Google sign-in was cancelled or failed.')

    state = request.args.get('state', '')
    if not verify_state(state, 'google'):
        return _oauth_error_redirect('Invalid or expired OAuth state. Please try again.')

    code = request.args.get('code', '')
    try:
        info  = google_get_user(code)
        user  = _oauth_upsert_user('google', info)
        token = generate_token(user['id'])
        params = urllib.parse.urlencode({
            'token':      token,
            'username':   user['username'],
            'has_bucket': '1' if user.get('s3_bucket') else '0',
        })
        return flask_redirect(f"{FRONTEND_URL}/auth/callback?{params}")
    except Exception as e:
        logger.error(f"Google callback error: {e}")
        return _oauth_error_redirect('Google sign-in failed. Please try again.')


# ── Email verification ────────────────────────────────────────────────────────

@app.route('/api/auth/verify-email', methods=['GET'])
def auth_verify_email():
    """Consume an email verification token."""
    token = request.args.get('token', '')
    if not token:
        return jsonify({'error': 'Token is required.'}), 400
    user_id = verify_email_token(token)
    if not user_id:
        return jsonify({'error': 'Token is invalid or has expired.'}), 400
    user = execute_query("SELECT id, username, email FROM users WHERE id = %s", (user_id,), fetch=True)
    return jsonify({'success': True, 'message': 'Email verified.', 'username': user[0]['username']}), 200


# ── Password reset ────────────────────────────────────────────────────────────

@app.route('/api/auth/forgot-password', methods=['POST'])
def auth_forgot_password():
    """Send a password-reset email. Always returns 200 (prevents email enumeration)."""
    data  = request.json or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'error': 'Email is required.'}), 400

    user = execute_query("SELECT id, email FROM users WHERE email = %s", (email,), fetch=True)
    if user:
        token = generate_reset_token(user[0]['id'])
        sent  = send_reset_email(email, token)
        if not sent:
            # Dev mode — return token so it can be tested without SMTP
            logger.info(f"[DEV] password reset token for {email}: {token}")

    return jsonify({
        'success': True,
        'message': 'If that email is registered, a reset link has been sent.',
    }), 200


@app.route('/api/auth/reset-password', methods=['POST'])
def auth_reset_password():
    """Set a new password using a reset token."""
    data     = request.json or {}
    token    = (data.get('token')    or '').strip()
    password = (data.get('password') or '').strip()

    if not token or not password:
        return jsonify({'error': 'Token and new password are required.'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters.'}), 400

    user_id = verify_reset_token(token)
    if not user_id:
        return jsonify({'error': 'Reset link is invalid or has expired.'}), 400

    execute_query(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (hash_password(password), user_id)
    )
    consume_reset_token(token)
    logger.info(f"Password reset for user {user_id}")
    return jsonify({'success': True, 'message': 'Password updated. You can now sign in.'}), 200


# ── Update /api/auth/signup to send verification email ───────────────────────
# (The signup route already exists above; we patch behaviour via the email module)
# When SMTP is configured, new email/password signups get a verification email.
# OAuth signups are auto-verified by the provider.


# Lambda WSGI handler — no mangum needed
import io, json

def handler(event, context):
    # Build WSGI environ from API Gateway v2 event
    body = event.get('body', '') or ''
    if event.get('isBase64Encoded'):
        import base64
        body = base64.b64decode(body)
    else:
        body = body.encode('utf-8')

    ctx = event.get('requestContext', {})
    http = ctx.get('http', {})
    method = http.get('method', 'GET')
    path = event.get('rawPath', '/')
    # Strip stage prefix if present (e.g. /prod/api/health -> /api/health)
    stage = ctx.get('stage', '')
    if stage and path.startswith('/' + stage):
        path = path[len('/' + stage):] or '/'
    query = event.get('rawQueryString', '')
    headers = event.get('headers', {}) or {}

    environ = {
        'REQUEST_METHOD':    method,
        'PATH_INFO':         path,
        'QUERY_STRING':      query,
        'CONTENT_LENGTH':    str(len(body)),
        'CONTENT_TYPE':      headers.get('content-type', ''),
        'SERVER_NAME':       'lambda',
        'SERVER_PORT':       '443',
        'wsgi.input':        io.BytesIO(body),
        'wsgi.errors':       io.StringIO(),
        'wsgi.url_scheme':   'https',
        'wsgi.multithread':  False,
        'wsgi.multiprocess': False,
        'wsgi.run_once':     False,
    }
    for k, v in headers.items():
        key = 'HTTP_' + k.upper().replace('-', '_')
        environ[key] = v
    if 'content-type' in headers:
        environ['CONTENT_TYPE'] = headers['content-type']

    response = {'status': '200 OK', 'headers': [], 'body': []}

    def start_response(status, response_headers, exc_info=None):
        response['status'] = status
        response['headers'] = response_headers

    result = app(environ, start_response)
    for data in result:
        response['body'].append(data)

    status_code = int(response['status'].split(' ', 1)[0])
    resp_headers = {k: v for k, v in response['headers']}
    body_bytes = b''.join(response['body'])

    return {
        'statusCode': status_code,
        'headers': resp_headers,
        'body': body_bytes.decode('utf-8'),
        'isBase64Encoded': False,
    }

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000, use_reloader=False)