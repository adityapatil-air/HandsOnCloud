<div align="center">

# HandsOnCloud

**Verifiable proof of your real-world AWS engineering experience.**

HandsOnCloud transforms your AWS CloudTrail logs into a shareable public profile — a GitHub-style contribution graph for cloud engineers — so recruiters, hiring managers, and clients can verify what you have actually *built* on AWS, not just what you claim on a résumé.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![AWS](https://img.shields.io/badge/AWS-CloudTrail-FF9900?logo=amazon-aws&logoColor=white)](https://aws.amazon.com/cloudtrail/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Status](https://img.shields.io/badge/status-active-success.svg)]()

[Live Demo](#) · [Documentation](#-documentation) · [Report a Bug](https://github.com/adityapatil-air/HandsOnCloud/issues) · [Request a Feature](https://github.com/adityapatil-air/HandsOnCloud/issues)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Why HandsOnCloud](#why-handsoncloud)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Running the Application](#running-the-application)
- [AWS Permissions](#aws-permissions)
- [User Flow](#user-flow)
- [Scoring Model](#scoring-model)
- [Security & Fraud Prevention](#security--fraud-prevention)
- [Performance](#performance)
- [API Reference](#api-reference)
- [Data Model](#data-model)
- [Deployment](#deployment)
- [Project Structure](#project-structure)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Support](#support)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Overview

**HandsOnCloud** is a full-stack platform that turns raw AWS activity into a credible, tamper-resistant public profile. It ingests CloudTrail logs directly from an S3 bucket you own, applies a multi-layer fraud-detection pipeline, scores every meaningful action against a curated rubric of **49 AWS services and 416 API actions**, and renders the result as a shareable contribution heatmap under a URL like `https://handsoncloud.io/<your-username>`.

The problem it solves is simple: **cloud engineering résumés are unverifiable.** Anyone can list "designed multi-region VPC architecture" as a bullet point. HandsOnCloud answers the harder question: *did they actually do it?*

## Why HandsOnCloud

| Traditional Résumé | HandsOnCloud Profile |
|---|---|
| Self-reported claims | Cryptographically verifiable from CloudTrail |
| Static list of technologies | Live activity graph across 365 days |
| No proof of depth | Weighted scores per service and action complexity |
| Trivially gameable | 3-layer fraud validation + AWS Account ID binding |
| Requires interview to assess | Recruiters get an instant, at-a-glance signal |

## Key Features

**Public verifiable profile.** A GitHub-style contribution heatmap over 365 days, credibility tier, service breakdown, and daily activity timeline — all on a single shareable URL.

**Fraud-resistant by design.** Three independent validation layers (ARN ownership, metadata integrity, random CloudTrail API sampling) combined with a `UNIQUE` constraint on the AWS Account ID make it structurally impossible to claim someone else's work.

**Curated scoring rubric.** 49 AWS services and 416 API actions weighted by real-world complexity — from `RunInstances` to `EKS CreateCluster` — with daily caps that reward consistent building over one-off bursts.

**Parallel CloudTrail ingestion.** A `ThreadPoolExecutor` pool downloads log files 10 at a time, cutting a typical sync from 15–20 minutes down to 2–3.

**Daily auto-sync.** A background scheduler keeps every profile fresh at 02:00 without user intervention.

**Enterprise-grade auth.** Email + password, GitHub OAuth, Google OAuth, JWT sessions, email verification, and password reset — plus a two-step signup that binds the account to a verified AWS identity before it is ever created.

**Encrypted credential vault.** AWS Access Keys and Secret Keys are stored under Fernet symmetric encryption and decrypted only at sync time — never exposed via API.

**Resource inventory.** Live view of the AWS resources you have provisioned, their current lifecycle state (running / stopped / terminated), and parent-child relationships (VPC → subnets, and so on).

## Architecture

```
                        ┌─────────────────────────────┐
                        │       Public Profile        │
                        │  handsoncloud.io/<user>     │
                        └─────────────┬───────────────┘
                                      │
                                      ▼
                        ┌─────────────────────────────┐
                        │   React 18 SPA  (:3000)     │
                        │   Heatmap · Dashboard · UI  │
                        └─────────────┬───────────────┘
                                      │  REST / JSON
                                      ▼
                        ┌─────────────────────────────┐
                        │   Flask REST API  (:5000)   │
                        │   Auth · Sync · Scoring     │
                        └──┬──────────┬──────────┬────┘
                           │          │          │
                ┌──────────▼──┐  ┌────▼─────┐  ┌─▼────────────┐
                │  Postgres / │  │  Fernet  │  │  Scheduler   │
                │   SQLite    │  │  Vault   │  │  (daily 02:00)│
                └─────────────┘  └────┬─────┘  └─┬────────────┘
                                      │          │
                                      ▼          ▼
                        ┌─────────────────────────────┐
                        │       AWS CloudTrail        │
                        │   S3 Logs · STS · Lookup    │
                        └─────────────────────────────┘
```

The frontend is a single-page React 18 application that consumes a stateless Flask REST API. The API authenticates requests with JWTs, persists user data in SQLite (development) or PostgreSQL (production), and pulls raw CloudTrail logs from the user's own S3 bucket over an assumed-role session. A separate scheduler process re-syncs every registered account daily.

## Technology Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18 · Axios · react-calendar-heatmap · React Router |
| **Backend** | Python 3.11+ · Flask · boto3 · Werkzeug · schedule |
| **Database** | SQLite (dev) · PostgreSQL (prod) |
| **Authentication** | JWT (HS256) · GitHub OAuth · Google OAuth |
| **Cryptography** | Fernet symmetric encryption (cryptography.io) |
| **AWS Services** | CloudTrail · S3 · IAM · STS |
| **CI/CD** | AWS CodeBuild (`buildspec.yml`) · CodeDeploy (`appspec.yml`) |

## Getting Started

### Prerequisites

- **Python** 3.11 or newer
- **Node.js** 18 or newer, with npm
- An **AWS account** with CloudTrail enabled and delivering to an S3 bucket
- (Optional) **PostgreSQL** 14+ for production-style local runs
- (Optional) SMTP credentials for email verification and password reset

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/adityapatil-air/HandsOnCloud.git
cd HandsOnCloud

# 2. Install backend dependencies
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Install frontend dependencies
cd ../frontend
npm install
```

### Configuration

Copy the example environment file and fill in the values:

```bash
cd backend
cp .env.example .env
```

```env
# ─── Database ───────────────────────────────────────────────
DB_ENGINE=sqlite                       # or "postgres"
DATABASE_URL=postgresql://user:pass@host:5432/handsoncloud

# ─── Auth ───────────────────────────────────────────────────
SECRET_KEY=change-me-to-a-long-random-string
JWT_EXPIRATION_HOURS=24

# ─── Email (optional) ───────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=noreply@yourdomain.com
SMTP_PASS=your-app-password

# ─── OAuth (optional) ───────────────────────────────────────
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# ─── URLs ───────────────────────────────────────────────────
FRONTEND_URL=http://localhost:3000
```

### Running the Application

Open two terminals:

```bash
# Terminal 1 — Backend API
cd backend
python app.py                          # http://localhost:5000

# Terminal 2 — Frontend SPA
cd frontend
npm start                              # http://localhost:3000
```

On Windows a convenience script is provided:

```bash
start-local.bat
```

To enable the daily background sync, run the scheduler as a third process (or a systemd unit / Windows Task Scheduler entry in production):

```bash
cd backend
python scheduler.py                    # fires at 02:00 daily
```

## AWS Permissions

The IAM user or role you supply needs the following minimum permissions. A ready-to-apply policy lives at `infrastructure/iam-policy.json`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetObject"],
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

## User Flow

1. Visit the app and land on `/login`.
2. Choose **Create account**.
3. Enter username, email, and password. *These are validated but no account is created yet.*
4. Enter AWS Access Key, Secret Key, and Region.
5. `sts:GetCallerIdentity` verifies the credentials and returns your AWS Account ID.
6. The Account ID is checked against the uniqueness constraint. If it is free, the account is created.
7. Redirect to `/setup` to select the CloudTrail S3 bucket.
8. Click **Start Sync**. Logs are downloaded, validated, scored, and persisted.
9. The profile page renders your heatmap, credibility tier, and service breakdown.
10. The daily scheduler keeps everything fresh going forward.

## Scoring Model

Scores are assigned per CloudTrail event by looking the `eventName` up in the `SCORING_RULES` dictionary in `backend/scoring.py`.

### Point Bands

| Points | Category | Representative Actions |
|:---:|---|---|
| **10** | Elite infrastructure | `eks:CreateCluster`, `cloudformation:CreateStack`, `emr:RunJobFlow` |
| **7–9** | High complexity | `rds:CreateDBInstance`, `ec2:CreateVpc`, `ecs:CreateService` |
| **5–6** | Medium complexity | `lambda:CreateFunction`, `iam:CreatePolicy`, API Gateway configuration |
| **3–4** | Standard operations | `s3:CreateBucket`, CloudWatch alarms, CodeBuild projects |
| **1–2** | Simple actions | `s3:PutObject`, `ec2:StartInstances`, `ec2:StopInstances` |
| **0** | Read-only (ignored) | `Describe*`, `Get*`, `List*`, `Head*`, `AssumeRole` |

### Daily Caps (Anti-Gaming)

```python
DAILY_SCORE_CAP   = 100    # Max total points per day
SERVICE_DAILY_CAP = 30     # Max points per service per day
ACTION_DAILY_CAP  = 15     # Max points per unique action per day
```

### Credibility Tiers

| Tier | Points Required |
|---|:---:|
| Beginner | 0 |
| Intermediate | 100 |
| Advanced | 500 |
| Expert | 1,500 |
| **Elite** | **5,000** |

### Tracked Services (49)

| Domain | Services |
|---|---|
| **Compute** | EC2, VPC, Lambda, ECS, EKS, ECR, Auto Scaling, Elastic Beanstalk, App Runner, Lightsail |
| **Storage** | S3, EFS, Backup |
| **Database** | RDS, DynamoDB, ElastiCache, Redshift, OpenSearch |
| **Security** | IAM, KMS, Secrets Manager, WAF, GuardDuty, Config |
| **Networking** | CloudFront, Route 53, ELB, Direct Connect |
| **Messaging** | SNS, SQS, Kinesis, Firehose |
| **DevOps** | CodePipeline, CodeBuild, CodeDeploy, CodeCommit |
| **Monitoring** | CloudWatch, CloudWatch Logs |
| **IaC & Ops** | CloudFormation, SSM |
| **Data & Analytics** | Glue, Athena, EMR |
| **ML** | SageMaker |
| **Workflow** | Step Functions |
| **API** | API Gateway |
| **Other** | Amplify, Transfer Family, IoT |

## Security & Fraud Prevention

Every design decision assumes an adversary is trying to inflate a score. The stack is layered so that defeating any single layer is not enough.

### 1. AWS Account ID Binding

At signup, `sts:GetCallerIdentity` returns the caller's AWS Account ID. That ID is written to the `users` table with a `UNIQUE` constraint. This makes it structurally impossible to spin up multiple profiles from the same AWS account — whether via the root user, a sub-IAM user, or a rotated key.

```
Attacker uses Person A's keys
  → STS returns Person A's Account ID: 751285160227
  → Database finds it already bound to @personA
  → Signup blocked
```

### 2. Three-Layer Log Validation

Every downloaded log file passes through three independent checks before any of its events are scored.

**Layer 1 — ARN ownership (instant).** Every CloudTrail event carries the ARN of the principal that performed it. The ARN's Account ID must match the registered Account ID; logs copied wholesale from another account are rejected.

**Layer 2 — Metadata integrity (instant).** `eventID` must be a valid UUID. `eventTime` must fall within ±2 hours of the timestamp embedded in the S3 object key. `sourceIPAddress` cannot be a localhost address. Hand-crafted logs fail these checks.

**Layer 3 — CloudTrail API sampling (fast).** 10% of scoreable events are re-fetched via `cloudtrail:LookupEvents`, AWS's authoritative source. If any sampled event does not round-trip, the entire file is rejected.

### 3. Event Deduplication

`eventID` has a `UNIQUE` constraint. Re-syncing never double-counts, and scores are durable even if the underlying S3 objects are later deleted.

### 4. Encrypted Credential Vault

AWS keys are encrypted at rest using Fernet symmetric encryption and only decrypted in-memory at sync time. They are never returned by any API endpoint.

### 5. Stateless JWT Auth

Protected endpoints require `Authorization: Bearer <token>`. Tokens are HS256-signed with a configurable expiry and never persisted server-side.

## Performance

**Parallel ingestion.** `concurrent.futures.ThreadPoolExecutor` downloads and parses S3 objects with 10 workers, delivering a roughly 10× speedup:

| Mode | Typical First Sync |
|---|---|
| Sequential (previous baseline) | 15–20 minutes |
| Parallel (current) | **2–3 minutes** |

**Incremental sync.** After the first sync, only objects newer than `processing_state.last_processed_timestamp` are fetched.

## API Reference

All endpoints are namespaced under `/api`. Protected endpoints require a bearer token.

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/preflight` | Validate username / email (no account created) |
| `POST` | `/api/auth/signup` | Create account after AWS verification |
| `POST` | `/api/auth/login` | Email + password login |
| `GET`  | `/api/auth/me` | Current user |
| `POST` | `/api/auth/logout` | Invalidate the current session |
| `GET`  | `/api/auth/github` | GitHub OAuth entrypoint |
| `GET`  | `/api/auth/google` | Google OAuth entrypoint |
| `POST` | `/api/auth/forgot-password` | Send password-reset email |
| `POST` | `/api/auth/reset-password` | Reset password with token |

### AWS Setup

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/credentials` | Save and verify AWS credentials |
| `GET`  | `/api/buckets` | List available S3 buckets |
| `POST` | `/api/buckets/select` | Choose the CloudTrail bucket |

### Sync

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sync` | Kick off an async sync job |
| `GET`  | `/api/sync/status/<job_id>` | Poll job progress |

### Public Profile

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/profile/<username>` | Full profile payload (heatmap, tier, totals) |
| `GET` | `/api/profile/<username>/dashboard` | Daily activity breakdown |
| `GET` | `/api/profile/<username>/resources` | Resource inventory |

### Health

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness / readiness probe |

## Data Model

```
users                          -- Accounts + encrypted AWS credentials + Account ID binding
activity_logs                  -- Individual scored AWS actions (unique on eventID)
daily_scores                   -- Pre-aggregated per-day totals (drives the heatmap)
processing_state               -- Per-user last_processed_timestamp
resource_state                 -- Live AWS resource inventory
email_verification_tokens
password_reset_tokens
```

## Deployment

The repository ships with AWS-native CI/CD scaffolding:

- **`buildspec.yml`** — AWS CodeBuild: installs dependencies, runs tests, produces build artifacts.
- **`appspec.yml`** — AWS CodeDeploy: orchestrates zero-downtime rollout to your compute layer.

For production, we recommend:

- **Backend** — containerize the Flask app and deploy behind an Application Load Balancer on **ECS Fargate** or **App Runner**. Terminate TLS at the ALB.
- **Frontend** — build with `npm run build`, serve as static assets from **S3** with **CloudFront** in front for edge caching.
- **Database** — **Amazon RDS for PostgreSQL** with automated backups and a Multi-AZ deployment.
- **Scheduler** — an **EventBridge** rule invoking an **ECS task** or **Lambda** on a daily cron.
- **Secrets** — **AWS Secrets Manager** for `SECRET_KEY`, database URL, OAuth client secrets, and SMTP credentials.

## Project Structure

```
HandsOnCloud/
├── backend/
│   ├── app.py                 # Flask REST API and route registration
│   ├── auth.py                # JWT generation and verification
│   ├── config.py              # Credibility tiers and constants
│   ├── credentials.py         # AWS credential encryption / decryption
│   ├── database.py            # DB connection and migrations
│   ├── emailer.py             # Verification and password-reset email
│   ├── ingestion.py           # CloudTrail parsing + parallel processing
│   ├── oauth.py               # GitHub & Google OAuth
│   ├── scheduler.py           # Daily auto-sync cron job
│   ├── scoring.py             # 49-service, 416-action scoring rules
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Auth.js
│   │   │   ├── AuthCallback.js
│   │   │   ├── ResetPassword.js
│   │   │   └── Setup.js
│   │   ├── App.js             # Public profile with heatmap
│   │   ├── Dashboard.js       # Daily activity breakdown
│   │   ├── Resources.js       # AWS resource inventory
│   │   ├── Visual.js          # Service activity timeline
│   │   ├── index.js           # Router and top-level layout
│   │   └── index.css
│   └── package.json
├── infrastructure/
│   ├── iam-policy.json        # Least-privilege IAM policy for users
│   └── trust-policy.json      # Cross-account role trust policy
├── scripts/                   # Operational and utility scripts
├── appspec.yml                # AWS CodeDeploy configuration
├── buildspec.yml              # AWS CodeBuild configuration
├── start-local.bat            # Convenience launcher (Windows)
└── README.md
```

## Roadmap

- [ ] **AWS Organizations** — first-class support for multi-account activity.
- [ ] **One-click IAM setup** — CloudFormation template that provisions the trust and permission policy in the user's account.
- [ ] **Résumé PDF export** — a printable, verifiable snapshot of your profile.
- [ ] **Badges & achievements** — surface milestones (first EKS cluster, first Multi-AZ RDS, and so on).
- [ ] **Team profiles** — aggregate activity across an engineering org.
- [ ] **Real-time ingestion** — S3 Event Notifications → SQS → worker, replacing polling.
- [ ] **Mobile app** — read-only companion for iOS and Android.
- [ ] **Public API** — issue scoped API keys so third parties can embed profiles.

### Known Limitations

- `cloudtrail:LookupEvents` only returns the trailing 90 days, which bounds Layer 3 sampling to that window.
- SQLite is fine for development but should not be used in production; switch to PostgreSQL.
- The scheduler currently runs as a standalone process; a managed runner (EventBridge + ECS/Lambda) is recommended for production.
- OAuth requires you to register applications with GitHub and Google separately.

## Contributing

Contributions of every kind — code, docs, bug reports, feature requests — are welcome.

1. **Fork** the repository.
2. **Create a feature branch:** `git checkout -b feature/your-feature`.
3. **Make your changes** with clear, atomic commits.
4. **Run the test suite** and lint before pushing.
5. **Open a Pull Request** describing what you changed, why, and how it was tested.

Please follow the existing code style, add tests for new behavior, and keep PRs focused. For non-trivial changes, open an issue first to discuss the approach.

## Support

- **Bug reports and feature requests:** open an [issue](https://github.com/adityapatil-air/HandsOnCloud/issues).
- **Security disclosures:** please do **not** open a public issue. Email the maintainer directly.
- **Questions:** GitHub Discussions is the best place for open-ended questions.

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for the full text.

## Acknowledgments

- **AWS CloudTrail** — the source of truth that makes verifiable proof possible.
- **react-calendar-heatmap** — the visualization component behind the contribution graph.
- **Flask** and **boto3** — the workhorses of the backend.
- Every cloud engineer who has ever had to argue on a call that yes, they have really built the thing they said they built.

---

<div align="center">

**Built to prove real AWS experience.**

If HandsOnCloud is useful to you, please consider starring the repository — it helps others find the project.

</div>
