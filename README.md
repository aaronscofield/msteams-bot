# Teams approval bot

A Microsoft Teams bot that sends **approval requests as Adaptive Cards** and records who approved or rejected
them — with the click verified four ways (Bot Framework signature, request binding, group membership, Teams SSO).

Python 3.14 · [Microsoft 365 Agents SDK](https://learn.microsoft.com/microsoft-365/agents-sdk/) (FastAPI hosting) · httpx · pydantic · uv.

## How it works

1. Something in your organisation calls `POST …/approvals` with a user and a request text.
2. The bot installs itself for that user if needed (Microsoft Graph), opens their 1:1 chat, and posts a card with
   **Approve / Reject** buttons (`Action.Execute`).
3. The user clicks. Teams delivers the click to `POST …/messages`; the bot runs its guards, records the decision,
   optionally POSTs it to a webhook, and replaces the card in place with the outcome.
4. For multi-approver flows, `PUT …/cards` turns the other approvers' cards into an "already decided by X" notice.

The bot never sends anything unprompted.

### How a click is verified

| guard | question | mechanism | config |
|---|---|---|---|
| 0 | Did this come from Microsoft? | Bot Framework JWT validated by the SDK (signature via Microsoft's JWKS, audience = the bot's app id) | always on |
| 1 | Is it a card we sent, answered once, by the addressee? | request id known and undecided · same conversation · clicker's Entra object id = addressee · token origin = activity origin | always on (`APPROVAL_TTL_HOURS`) |
| 2 | Is this person allowed to approve? | transitive membership of an Entra group (Graph, app-only) | `APPROVERS_GROUP_ID` + `GroupMember.Read.All` |
| 3 | Is this person who Teams says they are? | Teams SSO: an Entra-issued token for the bot's own API, validated by the bot; its `oid` must match the clicker | one-time setup below + `AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__SSO__*` |

Decisions carry `verifiedBy: "entra"` when SSO proved the identity, `"teams"` when it was only asserted by Teams.

## Layout

```
src/approval_bot/
  models/          pydantic models — settings · api (request/response bodies) · decision · pending
  config.py        load_settings / log_settings
  runtime.py       Agents SDK wiring: connection manager (cert → tokens), adapter, AgentApplication
  clients.py       GraphClient · ConnectorClient (httpx)
  store.py         PendingStore (in-memory)
  cards.py         request · result · notice Adaptive Cards
  guards.py        Refused · check_binding · check_group · check_sso (+ EntraTokenValidator)
  service.py       ApprovalService: create · update_card · decide
  handlers.py      Action.Execute routes on the SDK agent (+ dev /approval command)
  dependencies/    FastAPI dependencies: runtime · service · logger (X-Request-ID) · Bot Framework JWT · API key
  routers/         messages (Bot Framework) · approvals (trigger) · cards (update) · health
  server.py        app factory + entry point (uvicorn)
scripts/           send_approval.py · update_card.py · smoke_local.py
teams_app/         Teams app manifest + icons (not committed)  →  make package  →  dist/teams-app.zip
Dockerfile         python:3.14-slim + uv, non-root, health probe
Makefile           run · dev · smoke · approve · update-card · package · playground · lint · fmt · check · docker-*
```

## Prerequisites

- An **Azure Bot** resource with the Teams channel enabled, bound to a **SingleTenant Entra app registration**.
- A **certificate** registered on that app registration (the bot authenticates with it; no client secret needed for
  normal operation). Export it as `certs/bot.pfx`.
- The app registration granted (with admin consent) the Graph application permissions
  `TeamsAppInstallation.ReadWriteSelfForUser.All` and, for the group check, `GroupMember.Read.All`.
- The Teams app package uploaded to your **org app catalog** (see *Teams app* below).
- Locally: [uv](https://docs.astral.sh/uv/), Docker (optional), and the [Azure CLI](https://learn.microsoft.com/cli/azure/)
  for pointing the bot at your machine (see *Reaching the bot from Teams*).

## Setup

```bash
uv sync                  # creates .venv from uv.lock (Python 3.14)
cp .env.example .env     # fill in the ids; see the comments in the file
```

`.env` keys of note: the SDK's `CONNECTIONS__SERVICE_CONNECTION__SETTINGS__*` (client id, tenant id, auth type,
PFX path), `TEAMS_CATALOG_APP_ID`, `APPROVERS_GROUP_ID`, `APPROVAL_WEBHOOK_URL`, `APPROVALS_API_KEY`,
`API_DOMAIN` / `API_SUBDOMAIN` / `API_VERSION` (route prefix), and the SSO handler lines.

## Run

```bash
make run                 # bot on http://localhost:3978
make dev                 # dev flavour on :3979 — anonymous inbound, SSO/group off, /approval chat command, /docs
```

### Reaching the bot from Teams (dev tunnel)

Bot Framework must be able to POST to the bot, so a local bot needs a public HTTPS address. Card clicks are *invokes*
that need the bot's synchronous response, so use a **two-way** tunnel — Microsoft dev tunnels work well (ngrok does
too); one-way webhook relays such as smee.io do not.

```bash
brew install --cask devtunnel          # or: https://aka.ms/devtunnels (Windows/Linux)
devtunnel user login                   # Microsoft account or Entra sign-in
devtunnel create <tunnel-name> -a      # persistent tunnel; -a = anonymous access (Bot Framework can't authenticate to it)
devtunnel port create <tunnel-name> -p 3978 --protocol http
devtunnel host <tunnel-name>           # prints https://<id>-3978.<region>.devtunnels.ms — stable across restarts
```

Tunnel names are global to the service, so pick something unique. Keep `devtunnel host` running in its own terminal
next to `make run`. Then point the Azure Bot's **messaging endpoint** at the tunnel plus the route prefix:

```bash
az resource update --ids <azure bot resource id> \
  --set properties.endpoint="https://<id>-3978.<region>.devtunnels.ms/company/bot/v1/messages"
# resource id: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.BotService/botServices/<bot name>
```

The change is instant and global; a named tunnel keeps its URL, so this is a one-time step per tunnel. The same
`az resource update` is how you move the endpoint to a real deployment later. Note that the tunnel also exposes
`…/approvals` and `…/cards` publicly — set `APPROVALS_API_KEY` if that matters while it is up.

### Container

```bash
make docker-build
make docker-run          # passes .env; the PFX is injected as CERT_PFX_BASE64
make docker-logs
```

In production inject `CERT_PFX_BASE64` from a secret store (Key Vault, Secrets Manager, …) rather than a file.

## Use

```bash
make approve USER=someone@company.com TEXT="Deploy release 1.2.3"
# → sent ✔ {'requestId': …, 'conversationId': …, 'activityId': …, 'traceId': …}

make update-card CONV=<conversationId> ACT=<activityId> BY="Jane Doe" REQ=<requestId>
# → the card now reads "Already approved by Jane Doe"; late clicks on that request are refused
```

Both scripts are thin clients for the HTTP API; any HTTPS caller can do the same. Set `APPROVALS_API_KEY` to require
`Authorization: Bearer <key>` on `…/approvals` and `…/cards`. With `ENABLE_DOCS=true` (on in `make dev`) the full
request/response models are at `/docs`.

### Request correlation

Every request gets an `X-Request-ID` (yours if you send one, else generated), echoed on the response and stamped on
every log line as `[req=…]`. `ApprovalCreated.traceId` is the trigger's id; the decision log line and webhook payload
carry it as `traceId`, so a card's whole life can be grepped by one id.

## Test without Teams

```bash
make dev                 # terminal A
make smoke               # terminal B — fake Bot Connector; sends a card, clicks it, checks every refusal path
make playground          # or: Microsoft 365 Agents Playground UI; type "/approval <text>" and click the card
```

The Azure portal's *Test in Web Chat* exercises the real endpoint without Teams, but cannot do Teams SSO or supply
a real user identity.

## Teams app

`teams_app/` (manifest + icons) is deliberately untracked — it carries your app id and branding. Build it from the
[Teams app manifest schema](https://learn.microsoft.com/microsoftteams/platform/resources/schema/manifest-schema): `id` and
`bots[].botId` = the Entra app id, `bots[].scopes = ["personal"]`, and `webApplicationInfo` with `id` = the app id and
`resource = api://botid-<app id>`; `icons` `color.png` (192×192) and `outline.png` (32×32).

`make package` → upload `dist/teams-app.zip` in Teams admin center → Teams apps → Manage apps. Put the catalog
**App ID** shown there (not the *External app ID*) in `.env` as `TEAMS_CATALOG_APP_ID` — Graph only matches
installations by that id under the Self permission. The manifest's `webApplicationInfo.id` must equal the Entra
app id or installs fail with "Caller is not authorized". Bump `version` in `teams_app/manifest.json` on every change.

### Teams SSO (guard 3) — one-time setup

Teams can silently obtain an Entra token *for this bot's own API* on behalf of the user who clicks; the bot validates
it and requires its `oid` to match the clicker. That needs the app registration to expose an API, the Teams clients to
be pre-authorised for it, and the Azure Bot to hold an OAuth connection that can redeem the token. Tenant admin required.

**1. Expose an API** — Entra admin center → App registrations → *your bot app* → **Expose an API**
- **Application ID URI**: `api://botid-<app id>` (must equal `webApplicationInfo.resource` in the Teams manifest).
- **Add a scope**: `access_as_user`, *Admins and users* can consent, any display text — e.g. admin consent
  description "Allows Teams to call the bot's web APIs as the current user."
- **Add a client application** twice, ticking the scope for each: `1fec8e78-bce4-4aaf-ab1b-5451cc387264`
  (Teams desktop/mobile) and `5e3ce6c0-2b1f-4285-8d4b-75ee78787346` (Teams web). This pre-authorisation is what
  makes the sign-in silent.
- In **Manifest**, set `"accessTokenAcceptedVersion": 2` so the bot receives v2 tokens.

**2. Redirect URI** — same app → **Authentication** → Web platform → add
`https://token.botframework.com/.auth/web/redirect`. The Bot Framework token service performs the OAuth redirect on
the bot's behalf; without this Entra answers `AADSTS500113: No reply address is registered`.

**3. Client secret** — same app → **Certificates & secrets** → new secret (e.g. `teams-sso`). Azure Bot OAuth
connections need a secret; the bot itself keeps using the certificate for everything else.

**4. OAuth connection** — Azure portal → *your Azure Bot* → **Configuration** → *Add OAuth Connection Settings*:

| field | value |
|---|---|
| Name | `teams-sso` |
| Service provider | Azure Active Directory v2 |
| Client id / secret | the app id / the secret from step 3 |
| Token Exchange URL | `api://botid-<app id>` |
| Tenant ID | your tenant id |
| Scopes | `api://botid-<app id>/access_as_user openid profile` |

Save, then **Test Connection** — it should complete a browser sign-in as you. `AADSTS65005: scope … doesn't exist`
means the scope name here and in step 1 differ (hyphens vs underscores).

**5. Enable in the bot** — in `.env`:
```
AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__SSO__TYPE=UserAuthorization
AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__SSO__SETTINGS__AZUREBOTOAUTHCONNECTIONNAME=teams-sso
```
Restart; the startup log shows `Teams SSO enabled via auth handler 'SSO'`, and decisions log `"verifiedBy": "entra"`.
If a user sees a *Sign in* button instead of a silent completion, pre-authorisation has not propagated yet — clicking
it completes the same flow.

## Development

`make fmt` (ruff format + autofix) · `make check` (lint + format check, for CI). Config in `ruff.toml`.

Pending requests and the SDK's sign-in state live in memory: a restart voids outstanding cards, and multiple
instances would not share state. Swap `PendingStore` for a shared store before scaling out.
