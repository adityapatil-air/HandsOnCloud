# ☁️ HandsOnCloud

**Verify Your AWS Hands-On Experience**

CloudProof transforms your real AWS CloudTrail logs into a shareable public profile — like GitHub contributions but for cloud engineers. Recruiters can verify your actual AWS hands-on experience, not just resume claims.

---

## 🎯 What It Does

- Connects to your AWS S3 bucket where CloudTrail delivers logs
- Parses real AWS API calls you've made (RunInstances, CreateStack, etc.)
- Scores each action based on complexity and skill required
- Displays a GitHub-style activity heatmap on your public profile
- Shareable URL: `http://yourapp.com/username`

---

## 🏗️ Architecture

```
React Frontend (Port 3000)
        ↓ REST API
Flask Backend (Port 5000)
        ↓
   SQLite / PostgreSQL
        ↓
   AWS S3 (CloudTrail Logs)
```

---

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Axios, react-calendar-heatmap |
| Backend | Flask, boto3, Werkzeug |
| Database | SQLite (dev), PostgreSQL (prod) |
| AWS | CloudTrail, S3, IAM, STS |
| Auth | JWT tokens, OAuth (GitHub, Google) |
| Scheduling | Python `schedule` library |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- AWS account with CloudTrail enabled

### 1. Install Dependencies

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

### 2. Start Services

**Terminal 1 - Backend:**
```bash
cd backend
python app.py
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm start
```

Or use the batch script:
```bash
start-local.bat
```

- Backend: http://localhost:5000
- Frontend: http://localhost:3000

### 3. Run Auto-Sync Scheduler (Optional)

```bash
cd backend
python scheduler.py
```

Runs daily at 2:00 AM automatically for all users.

---

## 📁 Project Structure

```
cloudproof/
├── backend/
│   ├── app.py              # Flask REST API + all endpoints
│   ├── auth.py             # JWT token generation & verification
│   ├── config.py           # Credibility tiers configuration
│   ├── credentials.py      # AWS credential encryption/decryption
│   ├── database.py         # SQLite/PostgreSQL connection + migrations
│   ├── emailer.py          # Email verification & password reset
│   ├── ingestion.py        # CloudTrail log parsing + parallel processing
│   ├── oauth.py            # GitHub & Google OAuth
│   ├── requirements.txt    # Python dependencies
│   ├── scheduler.py        # Daily auto-sync cron job
│   └── scoring.py          # Activity scoring rules (49 services)
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Auth.js         # Login / Signup (2-step with AWS verification)
│   │   │   ├── AuthCallback.js # OAuth callback handler
│   │   │   ├── ResetPassword.js# Password reset page
│   │   │   └── Setup.js        # AWS credentials + bucket setup wizard
│   │   ├── App.js          # Profile page with heatmap
│   │   ├── Dashboard.js    # Daily activity breakdown
│   │   ├── index.css       # Dark theme styles
│   │   ├── index.js        # React router + routes
│   │   ├── Resources.js    # AWS resource inventory
│   │   └── Visual.js       # Service activity timeline
│   └── package.json
├── infrastructure/
│   ├── iam-policy.json     # Required IAM permissions
│   └── trust-policy.json   # Cross-account role trust policy
├── start-local.bat         # Start both services
└── README.md
```

---

## ✨ Features

### 🔐 Authentication
- Email + password signup/login
- GitHub OAuth
- Google OAuth
- JWT-based session management
- Email verification
- Password reset via email

### 👤 2-Step Signup (Fraud Prevention)
1. Enter username, email, password → validated but **no account created yet**
2. Enter AWS Access Key + Secret → STS verifies identity → **account created only if AWS Account ID is unique**

This prevents someone from creating multiple profiles with the same AWS account.

### 📊 Activity Heatmap
- GitHub-style contribution graph
- Shows daily AWS activity over 365 days
- Color intensity based on score
- Year selector for historical data
- Hover tooltips showing date + score

### 🏆 Credibility Tiers
| Tier | Points Required |
|------|----------------|
| Beginner | 0 |
| Intermediate | 100 |
| Advanced | 500 |
| Expert | 1,500 |
| Elite | 5,000 |

### 📈 Dashboard View
- Day-by-day activity breakdown
- Service grouping per day
- Individual action timestamps
- 7 / 30 / 90 day filter

### 🔧 Visual Timeline
- Service activity chips
- Action icons (create/delete/update)
- Chronological view

### 🏗️ Resource Inventory
- Tracks created AWS resources
- Shows current state (running/stopped/terminated)
- Parent-child relationships (VPC → Subnets)

### 🔄 Sync System
- **Manual sync**: Click "Sync from AWS" on profile (JWT authenticated)
- **Auto sync**: Daily at 2:00 AM via `scheduler.py`
- **Incremental**: Only processes new logs since last sync
- **Parallel**: Downloads 10 files simultaneously (10x faster)

---

## ⚙️ Scoring System

### How Scores Are Calculated

1. **CloudTrail log downloaded** from S3
2. **3-Layer fraud validation** (see Security section)
3. **Base score looked up** from `SCORING_RULES` dictionary
4. **Daily caps applied** to prevent gaming
5. **Stored in database** with deduplication

### Scoring Tiers

| Points | Category | Examples |
|--------|----------|---------|
| 10 | Elite Infrastructure | EKS CreateCluster, CloudFormation CreateStack, EMR RunJobFlow |
| 7-9 | High Complexity | RDS CreateDBInstance, EC2 CreateVpc, ECS CreateService |
| 5-6 | Medium Complexity | Lambda CreateFunction, IAM CreatePolicy, API Gateway |
| 3-4 | Standard Operations | S3 CreateBucket, CloudWatch Alarms, CodeBuild |
| 1-2 | Simple Actions | PutObject, Start/Stop instances |
| 0 | Read-Only (Ignored) | Describe*, Get*, List*, Head*, AssumeRole |

### Daily Caps (Anti-Gaming)

```python
DAILY_SCORE_CAP   = 100   # Max total points per day
SERVICE_DAILY_CAP = 30    # Max points per service per day
ACTION_DAILY_CAP  = 15    # Max points per action per day
```

### Tracked Services (49 Total, 416 Actions)

| Category | Services |
|----------|---------|
| Compute | EC2, VPC, Lambda, ECS, EKS, ECR, Auto Scaling, Elastic Beanstalk, App Runner, Lightsail |
| Storage | S3, EFS, Backup |
| Database | RDS, DynamoDB, ElastiCache, Redshift, OpenSearch |
| Security | IAM, KMS, Secrets Manager, WAF, GuardDuty, Config |
| Networking | CloudFront, Route53, ELB, Direct Connect |
| Messaging | SNS, SQS, Kinesis, Firehose |
| DevOps | CodePipeline, CodeBuild, CodeDeploy, CodeCommit |
| Monitoring | CloudWatch, CloudWatch Logs |
| IaC | CloudFormation, SSM |
| Data/Analytics | Glue, Athena, EMR |
| ML | SageMaker |
| Workflow | Step Functions |
| API | API Gateway |
| Other | Amplify, Transfer, IoT |

---

## 🛡️ Security Features

### 1. AWS Account ID Binding (Fraud Prevention)
When a user submits AWS credentials, we call `sts:GetCallerIdentity` which returns the AWS Account ID. This is stored with a `UNIQUE` constraint — one AWS account can only have one CloudProof profile.

```
Person B tries to use Person A's keys
→ STS returns Person A's Account ID: 751285160227
→ DB finds: already owned by @personA
→ BLOCKED ✅
```

**Covers all scenarios:**
- Person B uses Person A's root credentials → Blocked (same Account ID)
- Person B creates new IAM sub-user under Person A's account → Blocked (same Account ID)
- Person B creates entirely new AWS account → Allowed (different Account ID, different real scores)

### 2. Fake Log Detection (3-Layer Validation)

Every log file is validated before processing:

**Layer 1: ARN Ownership Check (Instant)**
- Every CloudTrail event contains the ARN of who performed it
- Verify it belongs to the registered AWS Account ID
- Catches logs copied from another account

**Layer 2: Metadata Validation (Instant)**
- `eventID` must be a valid UUID format
- `eventTime` must match the filename timestamp (±2 hours)
- No suspicious source IPs (127.0.0.1, localhost, etc.)
- Catches manually crafted fake logs

**Layer 3: Random API Sampling (Fast)**
- Randomly verify 10% of scoreable events via CloudTrail API
- CloudTrail API is AWS's authoritative source — cannot be faked
- Only checks non-read-only, scored events
- If any sampled event fails → entire file rejected

### 3. Event Deduplication
- Each CloudTrail event has a unique `eventID`
- Stored in DB with UNIQUE constraint
- Re-syncing never double-counts events
- Scores persist even if S3 logs are deleted

### 4. Encrypted Credentials
- AWS Access Key + Secret stored encrypted using Fernet symmetric encryption
- Never stored in plaintext
- Decrypted only at sync time, never exposed via API

### 5. JWT Authentication
- All protected endpoints require `Authorization: Bearer <token>`
- Tokens expire after configurable duration
- Stateless — no server-side session storage

---

## 🔌 API Endpoints

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/preflight` | Validate username/email (no account created) |
| POST | `/api/auth/signup` | Create account after AWS verification |
| POST | `/api/auth/login` | Login with email + password |
| GET | `/api/auth/me` | Get current user info |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/auth/github` | GitHub OAuth |
| GET | `/api/auth/google` | Google OAuth |
| POST | `/api/auth/forgot-password` | Send reset email |
| POST | `/api/auth/reset-password` | Reset password with token |

### AWS Setup
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/credentials` | Save + verify AWS credentials |
| GET | `/api/buckets` | List S3 buckets |
| POST | `/api/buckets/select` | Select CloudTrail bucket |

### Sync
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sync` | Start async sync job |
| GET | `/api/sync/status/<job_id>` | Poll sync progress |

### Profile
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/profile/<username>` | Full public profile |
| GET | `/api/profile/<username>/dashboard` | Daily activity breakdown |
| GET | `/api/profile/<username>/resources` | Resource inventory |

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |

---

## 🗄️ Database Schema

```sql
users               -- User accounts + AWS credentials
activity_logs       -- Individual scored AWS actions
daily_scores        -- Aggregated scores per day (for heatmap)
processing_state    -- Last sync timestamp per user
resource_state      -- AWS resource inventory
email_verification_tokens
password_reset_tokens
```

---

## ⚡ Performance

### Parallel Sync
Files are downloaded in parallel using `ThreadPoolExecutor` with 10 workers:

```
Before: Sequential processing = 15-20 minutes
After:  Parallel processing   = 2-3 minutes
```

### Incremental Sync
Only processes new log files since `last_processed_timestamp`:
- First sync: processes all historical logs
- Subsequent syncs: only new logs since last sync

---

## 🌐 Environment Variables

Create `backend/.env` from `backend/.env.example`:

```env
# Database (leave blank for SQLite)
DB_ENGINE=sqlite

# JWT
SECRET_KEY=your-secret-key-here

# Email (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@email.com
SMTP_PASS=your-app-password

# OAuth (optional)
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Frontend URL
FRONTEND_URL=http://localhost:3000
```

---

## 🔑 AWS Permissions Required

Your AWS IAM user needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::your-cloudtrail-bucket",
        "arn:aws:s3:::your-cloudtrail-bucket/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "cloudtrail:LookupEvents",
      "Resource": "*"
    }
  ]
}
```

---

## 📋 User Flow

```
1. Visit app → Redirected to /login
2. Click "Create account"
3. Enter username, email, password → Validated (no account yet)
4. Enter AWS Access Key + Secret Key + Region
5. STS verifies credentials + checks Account ID uniqueness
6. Account created + redirected to /setup
7. Select CloudTrail S3 bucket
8. Click "Start Sync" → CloudTrail logs processed
9. Profile page shows heatmap + scores
10. Daily auto-sync keeps profile updated
```

---

## 🚨 Known Limitations

- CloudTrail API verification limited to last 90 days of events
- SQLite not recommended for production (use PostgreSQL)
- Auto-sync scheduler must be run as a separate process
- OAuth requires configuring GitHub/Google app credentials

---

## 🔮 Future Improvements

- AWS Organizations support (multi-account)
- CloudFormation one-click IAM role setup
- PDF export for resume
- Badges and achievements
- Team profiles
- Mobile app
- Webhook-based real-time sync via S3 Event Notifications

---

## 👥 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit changes: `git commit -m "Add your feature"`
4. Push: `git push origin feature/your-feature`
5. Open a Pull Request

---

**Built with ❤️ to prove real AWS experience**
