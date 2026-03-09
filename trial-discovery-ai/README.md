# Acquittify Peregrine (Trial Discovery AI)

Defense-only, trial-first discovery intelligence system.

## What this folder is
This is the standalone Peregrine app scaffold (backend + frontend + docs). It is separate from the core Acquittify app and uses its own compose/env.

## Dev environment (Step 1)
- Docker compose stack: Postgres + Redis + MinIO
- Backend healthcheck (FastAPI)
- Frontend skeleton (Next.js)

## Phase 1 Local Activation
Use the activation script to bring up infra, apply migrations, and run auth/tenant smoke checks:

```bash
./trial-discovery-ai/scripts/phase1_activate_local.sh
```

Smoke test only (requires backend running on `http://127.0.0.1:8002`):

```bash
./trial-discovery-ai/scripts/phase1_smoke_auth.sh
```

## Phase 2 Local Activation
Phase 2 adds RBAC, password reset, CSRF protection, auth endpoint rate limiting,
integration tests, and CI workflow wiring.

Run the full local activation:

```bash
./trial-discovery-ai/scripts/phase2_activate_local.sh
```

Security smoke test only (requires backend running on `http://127.0.0.1:8002`):

```bash
./trial-discovery-ai/scripts/phase2_smoke_security.sh
```

## Phase 3 Local Activation
Phase 3 adds deployable containers (`api`, `worker`, `frontend`) and a
production rollout blueprint.

Run the full phase:

```bash
./trial-discovery-ai/scripts/phase3_activate_local.sh
```

Default local endpoints after startup:
- Frontend: `http://127.0.0.1:53000`
- API: `http://127.0.0.1:58002`

Validate a production env file before cloud deploy:

```bash
./trial-discovery-ai/scripts/phase3_preflight_env.sh /path/to/.env
```

Production blueprint:

- `trial-discovery-ai/docs/PHASE3_PRODUCTION_ROLLOUT.md`

## Phase 3b AWS Terraform
Phase 3b adds Terraform infrastructure for production AWS deployment.

Terraform stack:

- `deploy/terraform`

Run plan:

```bash
./trial-discovery-ai/scripts/phase3b_terraform_plan.sh
```

Apply:

```bash
./trial-discovery-ai/scripts/phase3b_terraform_apply.sh
```

Run migration task:

```bash
./trial-discovery-ai/scripts/phase3b_run_migration_task.sh
```

Phase 3b guide:

- `trial-discovery-ai/docs/PHASE3B_TERRAFORM_AWS.md`

## Next steps
Follow the build order in docs/MVP_SPEC.md.
