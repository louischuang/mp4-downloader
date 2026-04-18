# Deployment Scripts

This directory includes Docker image packaging scripts for pushing the app image to a container registry.

## Files

- `deploy.sh`
  Pushes an environment-specific tag.
- `deploy-latest.sh`
  Pushes `latest` and can also push the current package version tag.

## Environment Files

The scripts load environment variables in this order:

1. `.env.local`
2. `deploy/env/<environment>.env`

Supported environments:

- `dev`
- `staging`
- `prod`

Copy `.env.example` to `.env.local` and fill in your real registry settings.

## Required Variable

- `IMAGE_REGISTRY`

## Common Optional Variables

- `IMAGE_NAMESPACE`
- `IMAGE_NAME`
- `PLATFORMS`
- `BUILDER_NAME`
- `BUILD_CONTEXT`
- `DOCKERFILE_PATH`
- `APP_ENV`
- `IMAGE_TAG`
- `ALSO_TAG_VERSION`
- `DRY_RUN`

## Examples

Dry run:

```bash
DRY_RUN=true bash scripts/deploy.sh dev
DRY_RUN=true bash scripts/deploy-latest.sh prod
```

Push an environment tag:

```bash
bash scripts/deploy.sh dev
bash scripts/deploy.sh staging
bash scripts/deploy.sh prod
```

Push `latest`:

```bash
bash scripts/deploy-latest.sh prod
```

Push `latest` and the package version:

```bash
ALSO_TAG_VERSION=true bash scripts/deploy-latest.sh prod
```

## Resulting Tags

`deploy.sh` defaults to:

- `1.0.0-dev` for `dev`
- `1.0.0-staging` for `staging`
- `1.0.0` for `prod`

`deploy-latest.sh` defaults to:

- `latest`
- and also `1.0.0` when `ALSO_TAG_VERSION=true`

The version is always read from `package.json`.
