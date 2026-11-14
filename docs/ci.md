# CI conventions

## Commit messages

The repository uses [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(optional scope): <subject>
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
The first line is limited to 100 characters.

Enable the local hook once per clone:

```bash
git config core.hooksPath .githooks
```

CI runs `commitlint` on every pull request and also validates the pull request title, because squash merges use that title as the commit message.

## Workflows

- `actionlint` validates every workflow.
- Every `uses:` entry must be pinned to a full 40-character commit SHA with the release in a comment:

  ```yaml
  uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
  ```

- Local actions (`./...`) are allowed. Docker references (`docker://...`) must be pinned by digest.
- The pin check runs in CI and locally:

  ```bash
  ./scripts/check-actions-pinned.sh
  ```

To update an action, resolve the new tag to its commit SHA and update both the SHA and the comment:

```bash
git ls-remote https://github.com/actions/checkout 'refs/tags/v4.4.0' 'refs/tags/v4.4.0^{}'
```

The lint workflow lives in `.github/workflows/lint.yml`.

## Pull-request workflow

`.github/workflows/ci.yml` runs on every pull request and push to `main`. It is split into path-aware jobs so documentation-only changes stay lightweight while changes to Caddy, Compose or deployment scripts always run the edge checks.

| Job | Purpose | Runs when | Required check |
| --- | --- | --- | --- |
| `changes` | Detects changed paths for the rest of the workflow | always | no |
| `config` | Compose/Caddy validation, `actionlint`, action-pin check | backend, frontend, tests, Caddy, deploy, compose, scripts or workflow changes | yes |
| `unit` | Backend unit tests | backend or `tests/unit` changes | yes |
| `stack` | Integration, proxy, security and deploy-invariant checks against a real stack | backend, Caddy, deploy, compose, scripts or `tests/**` changes | yes |
| `e2e` | Playwright Use-Case suites | frontend, backend or `tests/e2e` changes | yes |
| `image` | Build the Pad image; push only on release tags | every PR/push | yes |
| `quality` | Coverage gates, coverage ratchet and Use-Case traceability | backend, frontend, tests or docs changes | yes |

The `lint.yml` workflow provides two additional required checks:

| Job | Purpose |
| --- | --- |
| `commits` | Conventional Commits and PR-title lint |
| `workflows` | `actionlint` and action-pin check |

### Concurrency and caching

- `concurrency` cancels in-progress runs for the same ref.
- `actions/setup-python` caches pip dependencies.
- `actions/setup-node` caches npm dependencies.
- `docker/build-push-action` uses GitHub Actions cache for layer caching.

### Least-privilege permissions

- The workflow defaults to `permissions: contents: read`.
- The `image` job is the only job that receives `packages: write`, and only when it runs.
- Registry authentication uses the automatic `GITHUB_TOKEN`; no SSH keys, application secrets or deployment credentials are used in PR workflows.
- Secret values are masked by GitHub Actions. Workflows never print `.env`, keys, tokens or certificates.

## Required checks and branch protection

> **Repository-admin action required.** The checks below must be marked as required in the `main` branch protection rules.

Required status checks for `main`:

1. `config`
2. `unit`
3. `stack`
4. `e2e`
5. `image`
6. `quality`
7. `commits` (from `lint.yml`)
8. `workflows` (from `lint.yml`)

Admin steps:

1. Go to **Settings > Branches > main > Protect this branch**.
2. Enable **Require a pull request before merging**.
3. Enable **Require status checks to pass before merging**.
4. Search for and select each required check name above.
5. Enable **Restrict who can push to matching branches** so all changes go through PRs.

Evidence to record:

- Screenshot of the branch protection rule showing the eight required checks.
- A test PR with a failing `config`, `unit`, `quality` or `lint` job showing the **Merge** button disabled.

## Image build and release recording

The `image` job in `ci.yml` builds the Pad image on every PR and push to `main` but only pushes to `ghcr.io/pad-ws/pad.ws` for release tags (`refs/tags/v*`).

- PR builds use `push: false` and still record the local digest in the job summary.
- Tag builds push a multi-platform image (`linux/amd64`, `linux/arm64`) and write a release manifest to `deploy/releases/<tag>.json`.
- The manifest contains the digest-pinned image reference, source run URL and timestamp.
- The manifest is uploaded as an artifact with 90-day retention.

Example release manifest (`deploy/releases/v1.2.3.json`):

```json
{
  "version": "v1.2.3",
  "digest": "sha256:abc123...",
  "image": "ghcr.io/pad-ws/pad.ws:v1.2.3",
  "digest_image": "ghcr.io/pad-ws/pad.ws@sha256:abc123...",
  "created": "2026-11-14T12:00:00Z",
  "source": "https://github.com/pad-ws/pad.ws/actions/runs/123456789"
}
```

Operators use the `digest_image` value during manual deployment and rollback.

## CI artifacts and summaries

Each job publishes a step summary and the relevant artifacts:

| Artifact | Contents | Retention |
| --- | --- | --- |
| `unit-test-results` | pytest JUnit XML | 14 days |
| `stack-test-results` | proxy/security JUnit XML | 14 days |
| `e2e-test-results` | Playwright report | 14 days |
| `coverage-reports` | backend XML/HTML, frontend summary/HTML, baseline | 14 days |
| `release-manifest-<tag>` | `deploy/releases/<tag>.json` | 90 days |

The `quality` job summary reports frontend and backend coverage percentages and links to the `coverage-reports` artifact. Failing jobs write the failing suite to the summary so the PR is diagnosable without downloading logs.

## Manual deployment and rollback

CI does **not** deploy to staging or production. Deployment and rollback are explicit operator actions performed outside CI using `scripts/deploy.sh` and the digest-pinned release manifest produced by the `image` job.

This change deliberately defers automated CD to a follow-up because it requires protected environments, deployment secrets, SSH or a self-hosted runner, backups and a release approval process. Until then:

- **Staging deploy:** operator runs `make deploy PROFILE=staging DOMAIN=... ALLOWLIST=...` with the desired digest set.
- **Production deploy:** operator runs `make deploy PROFILE=production ...` after staging acceptance.
- **Rollback:** operator runs `make rollback` using the previous digest set and backup recorded by the deploy script.

See `docs/deployment.md` for the exact commands and `openspec/changes/production-readiness-and-delivery/design.md` decision **D6** for the rationale.

## Verifying that failing checks block merge

To confirm the gates work, create a throw-away branch/PR for each failure mode and verify that GitHub disables merging:

| Failure mode | How to introduce | Expected result |
| --- | --- | --- |
| Lint | Push a commit with a non-Conventional-Commits subject, or use an unpinned action | `commits` / `workflows` fails |
| Unit test | Add `assert False` to a `tests/unit` test | `unit` fails |
| Coverage | Lower `.coveragerc` thresholds below the measured value, or remove a covered test | `quality` fails |
| Traceability | Change `docs/use-cases.md` status to `to implement` for a P0 UC | `quality` fails |

After verification, close the test PRs without merging. Record screenshots of the disabled **Merge** button as evidence.

## Local validation

Before pushing, validate workflow changes locally:

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/lint.yml'))"
./scripts/check-actions-pinned.sh
```

`actionlint` runs in CI. If it is installed locally you can also run:

```bash
docker run --rm -v "$PWD:/repo" -w /repo \
  rhysd/actionlint@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667
```
