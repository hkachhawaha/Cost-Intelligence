# Production Deployment & Hosting Architecture Guide

This document outlines the recommended hosting, deployment instructions, and cost projection for **Terzo Cost Intelligence** on **Vercel** and **Render**.

---

## 1. Target Architecture (Vercel & Render)

```mermaid
graph TB
    subgraph Frontend ["Vercel Host"]
        NextJS["Next.js Web Client<br/>(React App Router)"]
    end

    subgraph Backend ["Render Cloud Platform"]
        FastAPI["FastAPI App Container<br/>(API Port 8000)"]
        CeleryWorker["Celery Background Worker<br/>(AI matching & analytics)"]
        Postgres["Managed PostgreSQL<br/>(pgvector + RLS)"]
        Redis["Managed Redis<br/>(Celery Broker & Cache)"]
    end

    subgraph IDP ["External Services"]
        Auth0["Auth0 SSO IDP<br/>(JWT RS256 token verification)"]
        Gemini["Google Gemini API<br/>(Model Gateway / Embeddings)"]
    end

    %% Flow lines
    User((User Web Browser)) -->|HTTPS| NextJS
    User -->|HTTPS| FastAPI
    NextJS -->|SSO Login / Session| Auth0
    FastAPI -->|Authorize Claims| Auth0
    FastAPI -->|Queries| Postgres
    FastAPI -->|Cache / Queue Tasks| Redis
    CeleryWorker -->|Read Queue / Cache| Redis
    CeleryWorker -->|Queries| Postgres
    CeleryWorker -->|LLM calls| Gemini
```

---

## 2. Component Setup & Instructions

### Next.js Frontend (Vercel)
* **Build Command**: `pnpm --filter web build`
* **Output Directory**: `.next`
* **Required Environment Variables**:
  * `NEXT_PUBLIC_API_BASE`: URL of your Render FastAPI deployment (e.g., `https://cost-intelligence-api.onrender.com/api/v1`).
  * `AUTH0_SECRET`: Random 32-byte hex string.
  * `AUTH0_BASE_URL`: Vercel app domain (e.g., `https://your-app.vercel.app`).
  * `AUTH0_ISSUER_BASE_URL`: Your Auth0 domain (e.g., `https://tenant.us.auth0.com`).
  * `AUTH0_CLIENT_ID`: Auth0 Web Client ID.
  * `AUTH0_CLIENT_SECRET`: Auth0 Web Client Secret.

### FastAPI Backend & Celery Worker (Render)
Both backend components are built directly using your repository's Docker configuration.

#### 1. PostgreSQL Database
* Create a **Render PostgreSQL** database.
* Ensure pgvector is active (active by default in Render Postgres instances).

#### 2. Redis Instance
* Create a **Render Redis** instance (configured in Redis mode).

#### 3. FastAPI Web Service
* Create a **Web Service** on Render, pointing to your repo.
* **Runtime**: Docker
* **Docker Context**: Root of monorepo
* **Dockerfile Path**: `apps/api/Dockerfile`
* **Required Environment Variables**:
  * `ENVIRONMENT`: `production`
  * `DATABASE_URL`: Connection string of your Render Postgres database (e.g. `postgresql://...`).
  * `REDIS_URL`: Connection string of your Render Redis database (e.g. `rediss://...`).
  * `SECRETS_PROVIDER`: `redis` (dynamic token caching).
  * `AUTH0_DOMAIN`: Auth0 domain.
  * `AUTH0_AUDIENCE`: Auth0 Client Audience ID.
  * `GEMINI_API_KEY`: Google Gemini Developer API key.
  * `CORS_ALLOWED_ORIGINS`: Comma-separated list of allowed origins (e.g. `http://localhost:3000, https://your-app.vercel.app`).

#### 4. Celery Worker (Background Worker)
* Create a **Background Worker** on Render using the same repo.
* **Runtime**: Docker
* **Dockerfile Path**: `apps/api/Dockerfile`
* **Docker Start Command**: Override the default Docker CMD to run:
  ```bash
  uv run celery -A app.workers.ingestion_tasks worker --loglevel=info
  ```
* Binds the same environment variables as the Web Service (`DATABASE_URL`, `REDIS_URL`, etc.).

---

## 3. Sequential Deployment Guide (Backend First)

To deploy the stack correctly without circular dependencies, follow this step-by-step sequence:

### Step 1: Deploy the Backend on Render
1. Set up your **PostgreSQL** and **Redis** database services on Render.
2. Deploy the FastAPI **Web Service** and **Background Worker** using `apps/api/Dockerfile`.
3. Configure the required environment variables.
4. Configure CORS to accept temporary origins:
   * **Set `CORS_ALLOWED_ORIGINS` to**: `http://localhost:3000, https://*.vercel.app` (permits local testing and Vercel preview hostings).
5. Once the Web Service is active, copy the assigned public Render service URL (e.g., `https://your-api.onrender.com`).

### Step 2: Deploy the Frontend on Vercel
1. Set up a Next.js project on Vercel importing your monorepo.
2. In the project settings, configure the environment variables:
   * Set `NEXT_PUBLIC_API_BASE` to your deployed Render API URL (e.g., `https://your-api.onrender.com/api/v1`).
   * Complete the Auth0 parameters.
3. Deploy the frontend. Once active, copy the production frontend domain (e.g., `https://your-app.vercel.app`).

### Step 3: Lockdown & Finalize Security
1. Return to your **Render** dashboard for the FastAPI backend.
2. Update the `CORS_ALLOWED_ORIGINS` environment variable to lock it down exclusively to your production Vercel frontend domain:
   * **Set `CORS_ALLOWED_ORIGINS` to**: `http://localhost:3000, https://your-app.vercel.app` (removing the general wildcard).
3. In your **Auth0 Application Dashboard**, add your Vercel production domain to the **Allowed Callback URLs**, **Allowed Logout URLs**, and **Allowed Origins (CORS)** lists.

---

## 4. Cost Breakdown

Below is a detailed cost estimation for running the platform in a standard production environment:

| Service Provider | Component | Tier / Size | Estimated Monthly Cost | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Vercel** | Frontend App | Pro Plan | **$20.00** | Includes team collaboration, preview deployments, and global CDN. |
| **Render** | FastAPI API | Starter Web Service (512MB RAM, 0.5 CPU) | **$7.00** | Scales based on active requests. |
| **Render** | Celery Worker | Background Worker (512MB RAM, 0.5 CPU) | **$7.00** | Processes ingestion and AI matching jobs. |
| **Render** | PostgreSQL | Starter DB (1GB RAM, 0.25 CPU, 20GB SSD) | **$7.00** | Managed Postgres database with `pgvector` enabled. |
| **Render** | Redis Cache | Starter Redis (256MB RAM) | **$10.00** | Celery broker and transient secrets store. |
| **Auth0** | Identity Provider | B2C Essentials | **$23.00** | Paid tier required for custom domain SSL and compliance. |
| **Google** | Gemini API | Pay-as-you-go | **$15.00** | Estimate based on processing ~200 contracts/month. |
| **Total** | | | **$89.00 / month** | **Highly cost-effective baseline for production.** |
