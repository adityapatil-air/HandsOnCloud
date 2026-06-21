#!/bin/bash
# Run this ONCE manually after the CloudFormation stack is created
# to apply schema.sql to the RDS PostgreSQL database.
#
# Usage (from your local machine with psql installed):
#   export PGPASSWORD=<your-db-password>
#   bash scripts/after_install.sh
#
# Or run from an EC2 bastion / CloudShell with VPC access.

set -e

DB_HOST=$(aws ssm get-parameter --name /cloudproof/DB_HOST --region ap-south-1 --query Parameter.Value --output text)
SECRET=$(aws secretsmanager get-secret-value --region ap-south-1 --secret-id cloudproof-db-secret --query SecretString --output text)
DB_USER=$(echo $SECRET | python3 -c "import sys,json; print(json.load(sys.stdin)['username'])")
DB_PASS=$(echo $SECRET | python3 -c "import sys,json; print(json.load(sys.stdin)['password'])")
DB_NAME=$(echo $SECRET | python3 -c "import sys,json; print(json.load(sys.stdin)['dbname'])")

export PGPASSWORD=$DB_PASS

echo "Connecting to $DB_HOST..."
psql -h $DB_HOST -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME;" || true
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f backend/schema.sql
echo "Schema applied successfully."
