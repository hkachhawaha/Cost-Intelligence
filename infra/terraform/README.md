# Terraform — cloud foundation (outline)

Outline only; not applied for local Phases 1–4 (Docker Compose suffices). One
module per concern, composed in `environments/{dev,staging,prod}`.

```
infra/terraform/
├── modules/
│   ├── network/        # VPC, public+private subnets, NAT, security groups
│   ├── database/       # RDS Postgres 16 (pgvector param group), multi-AZ in prod.
│   │                   #   Creates a `migration` role WITH BYPASSRLS and an
│   │                   #   `app` role WITHOUT it (RLS enforcement guarantee).
│   ├── cache/          # ElastiCache Redis (cluster mode in prod)
│   ├── cluster/        # EKS (or GKE) + node groups; IRSA for pod IAM
│   ├── object_store/   # S3 bucket (versioned, SSE-KMS) for agent run snapshots
│   ├── secrets/        # AWS Secrets Manager entries (Auth0 secret, DB password,
│   │                   #   ANTHROPIC_API_KEY); outputs ARNs only — never values
│   ├── kms/            # per-tenant CMK strategy seed (encryption_key_ref source)
│   └── observability/  # managed Grafana/Datadog wiring; OTLP collector deploy
└── environments/
    ├── dev/
    ├── staging/
    └── prod/
```

## Principles

- Terraform emits secret **references** (ARNs) into k8s as env-from-secret; the
  app reads values at runtime via `SECRETS_PROVIDER=aws_sm`. **No plaintext
  secret ever lands in state.** Use a remote encrypted backend with restricted IAM.
- The **app runtime role has no `BYPASSRLS`**; only the migration role (used by
  Alembic in CI/CD) does. This guarantees RLS cannot be bypassed by the app.
- TLS 1.2+ terminated at the ingress/LB; internal traffic via the cluster mesh.

## Outputs surfaced to the app

`database_url_secret_arn`, `redis_url`, `s3_bucket`, `kms_key_arns`, `otel_endpoint`.
