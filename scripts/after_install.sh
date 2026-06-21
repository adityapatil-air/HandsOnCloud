#!/bin/bash
# Run this ONCE after the CloudFormation stack is created.
# Invokes a temporary Lambda to apply schema.sql to RDS (which is in a private subnet).
#
# Usage from CloudShell:
#   bash scripts/after_install.sh

set -e

REGION=ap-south-1
DB_HOST=$(aws ssm get-parameter --name /cloudproof/DB_HOST --region $REGION --query Parameter.Value --output text)
SECRET=$(aws secretsmanager get-secret-value --region $REGION --secret-id cloudproof-db-secret --query SecretString --output text)
DB_USER=$(echo $SECRET | python3 -c "import sys,json; print(json.load(sys.stdin)['username'])")
DB_PASS=$(echo $SECRET | python3 -c "import sys,json; print(json.load(sys.stdin)['password'])")

# Get Lambda VPC config from existing cloudproof-api Lambda
SUBNET=$(aws lambda get-function-configuration --function-name cloudproof-api --region $REGION --query 'VpcConfig.SubnetIds[0]' --output text)
SG=$(aws lambda get-function-configuration --function-name cloudproof-api --region $REGION --query 'VpcConfig.SecurityGroupIds[0]' --output text)
ROLE=$(aws lambda get-function-configuration --function-name cloudproof-api --region $REGION --query 'Role' --output text)

echo "Creating migration Lambda..."

# Download the full lambda.zip (has psycopg2 + all deps) from S3
BUCKET=$(aws ssm get-parameter --name /cloudproof/FRONTEND_BUCKET --region $REGION --query Parameter.Value --output text)
aws s3 cp s3://$BUCKET/lambda.zip /tmp/lambda.zip

# Write migration handler and add it into the existing zip
cat > /tmp/migrate.py << 'PYEOF'
import psycopg2, os

def handler(event, context):
    conn = psycopg2.connect(host=os.environ['DB_HOST'], port=5432,
        dbname='cloudproof', user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'])
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, username TEXT UNIQUE, name TEXT,
        email TEXT UNIQUE NOT NULL, password_hash TEXT,
        email_verified INTEGER DEFAULT 0, oauth_provider TEXT, oauth_id TEXT,
        s3_bucket TEXT, s3_prefix TEXT DEFAULT '', aws_region TEXT DEFAULT 'us-east-1',
        sync_pin_hash TEXT, aws_access_key_encrypted TEXT, aws_secret_key_encrypted TEXT,
        aws_account_id TEXT, aws_user_arn TEXT, last_auto_synced_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS activity_logs (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date DATE NOT NULL, service TEXT NOT NULL, action TEXT NOT NULL, score INTEGER NOT NULL,
        event_id TEXT, timestamp TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, event_id)
    );
    CREATE TABLE IF NOT EXISTS daily_scores (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date DATE NOT NULL, total_score INTEGER NOT NULL, UNIQUE(user_id, date)
    );
    CREATE TABLE IF NOT EXISTS processing_state (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        last_processed_timestamp TIMESTAMP NOT NULL, UNIQUE(user_id)
    );
    CREATE TABLE IF NOT EXISTS resource_state (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, parent_resource_id TEXT,
        state TEXT NOT NULL, metadata TEXT, last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, resource_type, resource_id)
    );
    CREATE TABLE IF NOT EXISTS email_verification_tokens (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token TEXT UNIQUE NOT NULL, expires_at TIMESTAMP NOT NULL,
        used INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token TEXT UNIQUE NOT NULL, expires_at TIMESTAMP NOT NULL,
        used INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_activity_logs_user_date ON activity_logs(user_id, date);
    CREATE INDEX IF NOT EXISTS idx_daily_scores_user_date ON daily_scores(user_id, date);
    """)
    cur.close(); conn.close()
    return {"status": "Schema applied successfully"}
PYEOF

# Add migrate.py into the full zip that already has psycopg2
cd /tmp && zip lambda.zip migrate.py

# Upload updated zip
aws s3 cp /tmp/lambda.zip s3://$BUCKET/migrate.zip

# Create Lambda using the full zip from S3
aws lambda create-function \
  --function-name cloudproof-migrate \
  --runtime python3.11 \
  --handler migrate.handler \
  --role $ROLE \
  --code S3Bucket=$BUCKET,S3Key=migrate.zip \
  --timeout 60 \
  --vpc-config SubnetIds=$SUBNET,SecurityGroupIds=$SG \
  --environment "Variables={DB_HOST=$DB_HOST,DB_USER=$DB_USER,DB_PASSWORD=$DB_PASS}" \
  --region $REGION 2>/dev/null || \
aws lambda update-function-code \
  --function-name cloudproof-migrate \
  --s3-bucket $BUCKET --s3-key migrate.zip \
  --region $REGION

echo "Waiting for Lambda to be ready..."
sleep 10

echo "Running migration..."
RESULT=$(aws lambda invoke --function-name cloudproof-migrate \
  --region $REGION --payload '{}' /tmp/migrate_result.json \
  --query 'FunctionError' --output text)

cat /tmp/migrate_result.json
echo ""

if [ "$RESULT" = "None" ] || [ -z "$RESULT" ]; then
  echo "Schema applied successfully!"
  echo "Cleaning up migration Lambda..."
  aws lambda delete-function --function-name cloudproof-migrate --region $REGION
else
  echo "Migration failed - check output above"
fi
