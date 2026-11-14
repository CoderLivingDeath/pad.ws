# Risk Register

This register tracks accepted risks and their governing controls for the
production-readiness-and-delivery change.

| ID | Risk | Severity | Owner | Mitigation / Control | Spec link |
|---|---|---|---|---|---|
| R-01 | Offsite backup and encryption are not implemented | High | Operator | Local timestamped backups with retention and `pg_restore --list` integrity checks; operator copies encrypted dumps off-site | `production-deployment` backup/restore |
| R-02 | Continuous deployment (CD) to staging/production is not automated | Medium | Project | CI runs all gates; deployment and rollback remain one-command operator actions documented in `docs/deployment.md` | `ci-cd` |
| R-03 | Edge rate limiting is not provided by the standard Caddy build | Medium | Project | Keycloak brute-force protection is enabled and verified; application-level rate limiting is a tracked follow-up | `application-security` rate-limiting posture |
| R-04 | Application-level login/API rate limiting is not implemented | Medium | Project | Documented follow-up after Keycloak brute-force protection; consider Redis counters or a custom Caddy build | `application-security` rate-limiting posture |

## Keycloak brute-force protection limits

The `pad` realm enables brute-force detection with the following settings,
enforced by `deploy/keycloak/realm-export.json` on a fresh database and by the
idempotent `deploy/keycloak/bootstrap-brute-force.sh` script on existing
databases:

- `bruteForceProtected`: `true`
- `failureFactor`: `5`
- `maxDeltaTimeSeconds`: `300`
- `minimumQuickLoginWaitSeconds`: `60`
- `waitIncrementSeconds`: `60`
- `maxFailureWaitSeconds`: `900`
- `permanentLockout`: `false`

These limits are verified by `tests/security/test_brute_force.py`.
