# Company Teams approval bot — common tasks
IMAGE    ?= teams-bot
VERSION  ?= $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)

.PHONY: run dev smoke update-card approve tilt-up tilt-down package playground lint fmt check docker-build docker-run docker-stop docker-logs

run:            ## run the bot locally on :3978
	uv run python -m approval_bot

update-card:    ## replace a card: make update-card CONV=a:… ACT=1787… BY="Jane Doe" [TEXT=… REQ=<requestId>]
	uv run scripts/update_card.py $(CONV) $(ACT) --by $(BY) $(if $(TEXT),--text $(TEXT)) $(if $(REQ),--request-id $(REQ))

approve:        ## send an approval card: make approve USER=who@company.com TEXT="Deploy 1.2.3"
	uv run scripts/send_approval.py $(USER) $(TEXT)

package:        ## build dist/teams-app.zip from teams_app/
	@mkdir -p dist && rm -f dist/teams-app.zip && cd teams_app && zip -q -j ../dist/teams-app.zip manifest.json color.png outline.png && echo "built dist/teams-app.zip"

dev:            ## bot on :3979 for the Playground: anonymous inbound, SSO + group check off, /approval command, /docs on
	DEV_COMMANDS=true DISABLE_SSO=true ENABLE_DOCS=true APPROVERS_GROUP_ID= PORT=3979 \
	CONNECTIONS__SERVICE_CONNECTION__SETTINGS__ANONYMOUS_ALLOWED=true uv run python -m approval_bot

smoke:          ## local smoke test against `make dev` (fake connector, no Teams)
	uv run scripts/smoke_local.py

playground:     ## Microsoft 365 Agents Playground against the dev bot (no Azure, no Teams)
	npx --yes @microsoft/teams-app-test-tool -e http://localhost:3979/company/bot/v1/messages

lint:           ## ruff lint
	uv run ruff check .

fmt:            ## ruff format + autofix
	uv run ruff format . && uv run ruff check . --fix

check:          ## CI-style: lint + format check
	uv run ruff check . && uv run ruff format --check .

tilt-up:        ## dev loop: rebuild/restart containers on change (UI at http://localhost:10350)
	tilt up

tilt-down:      ## stop the Tilt-managed stack
	tilt down

docker-build:   ## build the container image
	docker build -t $(IMAGE):$(VERSION) -t $(IMAGE):latest .

docker-run:     ## run the container on :3978 with .env and the cert passed as base64
	docker rm -f $(IMAGE) >/dev/null 2>&1 || true
	docker run -d --name $(IMAGE) --env-file .env -e CERT_PFX_BASE64="$$(base64 -i certs/bot.pfx)" -p 3978:3978 $(IMAGE):latest

docker-stop:
	docker rm -f $(IMAGE)

docker-logs:
	docker logs -f $(IMAGE)
