# Security & Tenant Isolation Guide (Vercel & Render)

This document details the security architecture, authorization design, and tenant isolation policies enforced when deploying **Terzo Cost Intelligence** on Vercel and Render.

---

## 1. Network & Ingress Security

```
User Browser ────(HTTPS)────► Vercel (Next.js Frontend)
     │
     └───────────(HTTPS)────► Render Service (FastAPI Backend)
```

* **TLS Termination**: All public traffic terminates TLS 1.2+ at Vercel (for frontend) and Render's load balancer (for backend).
* **CORS Policies**: The FastAPI backend configures CORS rules restricting incoming origins exclusively to the verified Vercel production domain (`https://cost-intelligence-web.vercel.app`).

---

## 2. Multi-Tenant Row Level Security (RLS)

PostgreSQL Row Level Security is the primary defense against cross-tenant data bleed.

### Database Roles Separation
To ensure RLS cannot be bypassed at runtime:
1. **The `app` Role (Render Web Process)**:
   * Has standard `SELECT`, `INSERT`, `UPDATE`, `DELETE` privileges.
   * **Does NOT** have the `BYPASSRLS` attribute.
   * All queries executed by the FastAPI web service automatically go through RLS policies.
2. **The `migration` Role (CI/CD / Release Task)**:
   * Has `BYPASSRLS` and DDL privileges.
   * Used strictly to apply Alembic migrations during build or release phases.

### RLS Session Setup
Every session created by the FastAPI backend sets the tenant context before executing queries:
```sql
SET LOCAL app.current_tenant = :tenant_id;
```
If no session context is active, queries default to returning **zero rows** (fail-closed security posture).

---

## 3. Authentication & JWT Validation

The application utilizes **Auth0** for user identity:
* **JWT Claims**: Auth0 signs user tokens containing custom namespace claims including `tenant_id` and `roles`.
* **RS256 Pinned Signature**: The API only accepts JWTs signed using the RS256 algorithm. Symmetric token validations are rejected.
* **JWKS Caching**: Public keys are loaded from Auth0's JWKS endpoint and cached in memory. If a token presents an unknown Key ID (`kid`), the keys are fetched once to handle key rotations.

---

## 4. Secrets Management

* **No Plaintext Configuration**: Credentials and secret keys (`AUTH0_CLIENT_SECRET`, `GEMINI_API_KEY`, database connection passwords) are never committed to git.
* **Environment Injection**: Production parameters are injected directly into Render's service environment settings and mapped to container environments.
* **Redis Caching for Dynamic Tokens**: Refresh tokens and dynamic connection details are encrypted and stored in a shared Redis cache (using the `redis` secrets provider), preventing file leaks on Render's ephemeral container disks.
