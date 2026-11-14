# Bug report — публичный тестовый стенд

**Дата:** 2026-11-13
**Стенд:** `/home/agent/pad-public-test`
**Домены:** `pad.176.100.36.107.sslip.io`, `auth.176.100.36.107.sslip.io`, `coder.176.100.36.107.sslip.io`
**Коммиты:** `5bb03d7`, `69802f7`, `1798652`, `900a80f`, `d5ce51c`
**Статус:** стенд развёрнут, Pad/Keycloak/Coder healthy, workspace создаётся автоматически, терминал работает.

## Сводка

| ID | Severity | Область | Симптом | Статус |
| --- | --- | --- | --- | --- |
| BUG-001 | Critical | Pad runtime | Pad не стартует: `No module named 'greenlet'` | Fixed, verified |
| BUG-002 | Critical | Coder local | Coder не проходит OIDC discovery / не доверяет Caddy CA | Fixed, verified |
| BUG-003 | Critical | Keycloak realm | OIDC login падает: нет `sub`, scopes, пользовательские ID не UUID | Fixed, verified |
| BUG-004 | Medium | Auth redirects | `/api/auth/login` возвращает 307 вместо 302 | Fixed, verified |
| BUG-005 | High | WebSocket | `forward_auth` пробрасывает `Upgrade`, verify обрабатывается как WebSocket | Fixed, verified |
| BUG-006 | High | Coder agent | Агент не может скачать `/bin/coder-linux-amd64` (401) | Fixed, verified |
| BUG-007 | Critical | Coder agent | `/derp` за `forward_auth`: агент не подключается, `no_handshake` | Fixed, verified |
| BUG-008 | High | Coder UI | `/assets/*` Coder отдают 401 → MIME-ошибки JS/CSS | Fixed, verified |
| BUG-009 | High | Coder OIDC | `AuthGate` удаляет priming-iframe до завершения OIDC | Fixed, verified |
| BUG-010 | High | Workspace API | `/api/workspace/state` отдаёт 500 при невалидном Coder API key | Fixed, verified |
| BUG-011 | Medium | Dashboard | Dashboard не рендерится без workspace | Fixed, verified |
| BUG-012 | Critical | Pad persistence | Изменения доски теряются при переключении вкладок | Fixed, verified |
| BUG-013 | High | Session | Pad-сессия истекает через 30 минут, `/api/*` отдаёт 401 | Fixed, pending reload |
| BUG-014 | High | Coder apps | code-server assets `/@.../apps/...` за Pad-gate → 401 JSON | Fixed, pending reload |
| BUG-015 | Medium | Operations | Coder API key живёт максимум 7 дней | Open, documented |
| BUG-016 | Low | Coder routing | Терминал открывали по `.agent` вместо `.main` | Fixed, documented |

## Детали

### BUG-001 — отсутствует `greenlet` в runtime-образе

**Симптом:** контейнер `pad` падает на импорте `sqlalchemy.ext.asyncio`.

**Причина:** `greenlet` был добавлен только в `requirements-dev.txt`, но SQLAlchemy async требует его в runtime.

**Fix:** добавлен `greenlet` в `src/backend/requirements.txt`.

**Проверка:** Pad healthy, `/` и `/api/auth/verify` отвечают.

### BUG-002 — Coder не может использовать публичный issuer в local-режиме

**Симптом:** `dial tcp: lookup auth.pad.test` и `issuer URL ... did not match`.

**Причина:** Coder-контейнер не резолвил `*.pad.test`; внутренний issuer не совпадал с публичным.

**Fix:** local-профиль использует публичный issuer через Caddy, `extra_hosts` + `host-gateway`, монтирует Caddy root CA, Caddy стартует раньше Coder; Coder ждёт healthy Keycloak.

**Проверка:** Coder healthy, OIDC login через `OpenID Connect` работает, workspace provisioner запускается.

### BUG-003 — неполный Keycloak realm export

**Симптом:** `invalid_scope: openid profile email`, затем `KeyError: 'sub'`, затем `badly formed hexadecimal UUID string`.

**Причина:** в тестовом realm отсутствовали стандартные client scopes, `sub`-маппер; ID пользователей были строками `user-admin`.

**Fix:** добавлены claim-мапперы (`sub`, `preferred_username`, `email`, `email_verified`, `name`, `realm_access.roles`), scope `openid`, UUID для тестовых пользователей, `directAccessGrantsEnabled=false`.

**Проверка:** integration login/callback 10/10 passed; Pad создаёт пользователя и сессию.

### BUG-004 — 307 вместо 302

**Симптом:** integration-тест ожидал 302 от `/api/auth/login`.

**Fix:** `RedirectResponse(..., status_code=302)` для login и callback.

### BUG-005 — verify получает Upgrade при WebSocket

**Симптом:** в логах Pad `WebSocket /api/auth/verify 403`, Pad WS не поднимается.

**Причина:** Caddy `forward_auth` передавал `Upgrade`/`Connection` в auth-subrequest.

**Fix:** в `forward_auth` добавлены `header_up -Upgrade` и `header_up -Connection`.

**Проверка:** Pad collaboration WebSocket test passed.

### BUG-006 — агент не скачивает бинарник

**Симптом:** workspace-контейнер повторяет `curl ... /bin/coder-linux-amd64` → 401.

**Причина:** `/bin/*` был за `forward_auth`.

**Fix:** `/bin/*` добавлен в публичные пути Coder-хоста.

### BUG-007 — агент не подключается к DERP

**Симптом:** Coder API: `agent is unreachable`, `reason=no_handshake`, `peer_rx_bytes=0`.

**Причина:** `/derp` был за `forward_auth`; агент не мог открыть DERP WebSocket.

**Fix:** `/derp` и `/derp/*` добавлены в Coder API bypass.

**Проверка:** agent status `connected`, health `true`, `/derp` отвечает `426 Upgrade Required` (ожидаемо).

### BUG-008 — Coder static assets 401

**Симптом:** `/assets/clsx...`, `radix-ui...`, `monaco...` → 401, MIME `application/json`.

**Причина:** статика Coder шла через `forward_auth`; при cross-site cookie ограничениях Pad-cookie не отправлялась.

**Fix:** `/assets/*`, `/static/*`, `/favicon.ico` публичны на Coder-хосте; UI и API остаются защищены.

### BUG-009 — Coder OIDC priming обрывался

**Симптом:** Pad открывал Coder login вместо терминала.

**Причина:** `AuthGate` удалял iframe по первому `onload`, то есть после первого редиректа Coder → Keycloak.

**Fix:** iframe живёт 15 секунд, URL получил `?redirect=%2F`.

**Проверка:** после логина Pad в браузере появляется `coder_session_token`; Pad embedded terminal iframe открывается на `.main`.

### BUG-010 — 500 при невалидном Coder API key

**Симптом:** `/api/workspace/state` → 500, traceback `401 Client Error: Unauthorized` из Coder API.

**Fix:** Coder API ошибки обрабатываются как `503`; для отсутствующего workspace возвращается `200` с `state=stopped`; `start/stop` без workspace → `409`.

**Проверка:** с валидным ключом `/state` → `200`; после создания workspace → `running`.

### BUG-011 — dashboard не рендерится без workspace

**Симптом:** `Error loading workspace status`.

**Fix:** синтетическое состояние `stopped` + явный `409` при попытке запуска без workspace.

### BUG-012 — изменения доски теряются при переключении pad

**Симптом:** нарисованное не сохраняется после переключения вкладки и возврата.

**Причина:** при смене pad старый WebSocket закрывался без контрольной записи; последние сообщения могли не дойти до worker/БД.

**Fix:**
- `PUT /api/pad/{id}/data` — checkpoint `elements`/`files` в БД и Redis;
- frontend сохраняет текущую сцену перед `selectTab` и перед созданием нового pad;
- `Collab` отправляет полный `SCENE_UPDATE` в старый сокет перед disconnect.

**Проверка:** сцена из 21 элемента отправляется `PUT` при переключении и остаётся 21 после возврата.

### BUG-013 — 30-минутная Pad-сессия

**Симптом:** после работы в Coder `/api/workspace/state` начинает отдавать 401 несколькими retry.

**Причина:** Keycloak `ssoSessionIdleTimeout=1800`, Pad cookie Max-Age = refresh lifetime.

**Fix:** для тестового realm установлено:
- `ssoSessionIdleTimeout=28800` (8h);
- `ssoSessionMaxLifespan=604800` (7d);
- `clientSessionIdleTimeout=28800`;
- `clientSessionMaxLifespan=604800`.

Плюс frontend `useWorkspace` при 401 перенаправляет на `/api/auth/login?rd=...`.

### BUG-014 — code-server assets за Pad-gate

**Симптом:** `/@admin/ubuntu.main/apps/code-server/.../workbench.css` и JS отдают 401 JSON, браузер ругается на MIME.

**Причина:** workspace app paths не входили в Coder API bypass.

**Fix:** `/@*` добавлен в Coder bypass; Coder сам аутентифицирует workspace apps. Pad-gate остаётся на Coder UI `/`.

**Проверка:** без Pad-cookie запрос отдаёт 303 от Coder на login, а не 401 JSON от Caddy. С Coder-сессией assets загружаются.

**Residual risk:** workspace apps больше не защищены Pad-сессией на edge; их защищает Coder. Это осознанный компромисс для iframe/code-server.

### BUG-015 — срок жизни Coder API key

**Симптом:** через 7 дней `/api/workspace/state` снова начнёт отдавать 503.

**Причина:** Coder ограничивает token lifetime 168h.

**Action:** обновлять `CODER_API_KEY` в `.env` и перезапускать `pad`. Добавлено в runbook.

### BUG-016 — `.agent` вместо `.main`

**Симптом:** `Trying to connect...` при открытии `/@admin/ubuntu.agent/terminal`.

**Причина:** агент шаблона называется `main`; `.agent` — неверный путь.

**Fix:** Pad формирует путь из `workspaceState.agent` (`main`); документация обновлена.

## Что проверено после фиксов

- `openspec validate --strict` — OK.
- Unit: 49 passed.
- Integration: 10 passed.
- Proxy/security: 27 passed, 3 skipped.
- E2E: login, return path, pad CRUD, WebSocket, logout, replay, switch user — passed.
- Smoke: 11 passed.
- Coder workspaces: `admin/ubuntu` и `user26036/ubuntu` — `running`, agent `connected`, health `true`.
- Pad embedded terminal: iframe `.main`, `.xterm` отображается.
- Публичные сертификаты Let's Encrypt для трёх доменов.

## Открытые ограничения тестового стенда

- `ADMIN_ALLOWLIST` открыт (`0.0.0.0/0 ::/0`); Keycloak admin всё ещё требует роль и master-пароль.
- Coder OIDC signups включены; первый пользователь становится owner.
- Тестовые пароли и API key лежат в `/home/agent/pad-public-test/credentials.txt` и `.env` (mode 600).
- Backup/offsite/monitoring и ротация секретов остаются follow-up.
- Домены `sslip.io` привязаны к IP `176.100.36.107`.

## BUG-017 — code-server `vsda` 404 (upstream)

**Симптом:** в консоли code-server:

```
/vsda/rust/web/vsda.js 404
/vsda/rust/web/vsda_bg.wasm 404
Refused to execute script ... MIME type ('text/plain')
```

**Причина:** code-server 4.145.2 в workspace-образе не содержит пакет
`vsda` в `static/node_modules/vsda/rust/web/`. Это upstream-особенность
сборки code-server, не ошибка Pad/Caddy.

**Влияние:** ошибки в консоли, Microsoft/VSDA-аутентификация в code-server
не используется; редактор и терминал работают.

**Решение:** не маскировать 404 на Caddy (иначе сломается VSDA, если пакет
появится). Зафиксировать как upstream-шум; при обновлении code-server
перепроверить.

## Финальная проверка после исправлений

- `GET /api/workspace/state` → `200`, `state=running`, `username=admin`,
  `agent=main`.
- Pad session cookie присутствует, 401 на `/api/workspace/state` больше нет.
- Coder terminal `@admin/ubuntu.main/terminal` открывается, `.xterm` найден.
- code-server `@admin/ubuntu.main/apps/code-server/` открывается, title
  `coder - code-server`.
- В консоли после логина и открытия терминала: **нет** `PostHog not yet
  initialized`, **нет** 401/502.
- Единственные оставшиеся 4xx — два upstream-404 `/vsda/*`.
