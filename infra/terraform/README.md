# Azure infrastructure for the approval bot

Creates everything on the Microsoft side that `src/approval_bot` needs. Nothing here runs code — hosting the bot
(container on App Runner / Container Apps / a VM) is separate.

| resource | what it is |
|---|---|
| `azuread_application.bot` + service principal | The bot's identity: SingleTenant app registration, certificate credential, declared Graph permissions, the redirect URI Bot Framework's token service needs |
| `azuread_app_role_assignment.graph` | Admin consent for `TeamsAppInstallation.ReadWriteSelfForUser.All` (+ `GroupMember.Read.All` when `enable_group_check`) |
| `azuread_application_identifier_uri` / `oauth2_permission_scope` / `pre_authorized` | Teams SSO: exposes `api://botid-<app>/access_as_user` and pre-authorises the Teams clients so sign-in is silent |
| `azuread_application_password.sso` | Client secret used only by the Azure Bot OAuth connection (the bot itself authenticates with the certificate) |
| `azurerm_bot_service_azure_bot.bot` | The Azure Bot (global, SingleTenant) with its messaging endpoint |
| `azurerm_bot_channel_ms_teams.teams` | Teams channel |
| `azurerm_bot_connection.teams_sso` | OAuth connection (Azure AD v2) with the token-exchange URL and scopes |

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in ids; keep terraform.tfvars out of git
terraform init
terraform plan
terraform apply
terraform output env_snippet                   # paste into the bot's .env
```

Run as a user who can create app registrations and grant admin consent (Application Administrator or Global
Administrator) and who has Contributor on the subscription/resource group. `az login` first; the providers use
the Azure CLI credentials.

## Certificate

Generate once (private key stays on the bot host as `certs/bot.pfx`; Terraform registers only the public half):

```bash
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes -keyout certs/bot-key.pem -out certs/bot-cert.pem -subj "/CN=<bot name>"
openssl pkcs12 -export -inkey certs/bot-key.pem -in certs/bot-cert.pem -out certs/bot.pfx -passout pass:
openssl x509 -in certs/bot-cert.pem -noout -enddate      # → certificate_end_date
```

## Adopting existing resources

If the app registration and bot already exist, import them instead of creating duplicates:

```bash
terraform import azuread_application.bot /applications/<application object id>
terraform import azuread_service_principal.bot <service principal object id>
terraform import azurerm_bot_service_azure_bot.bot /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.BotService/botServices/<bot name>
terraform import azurerm_bot_channel_ms_teams.teams /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.BotService/botServices/<bot name>/channels/MsTeamsChannel
```

Then `terraform plan` shows the drift (e.g. the redirect URI or a missing scope) and `apply` reconciles it.

## After apply

- Put `client_id` into the Teams manifest (`id`, `bots[].botId`, `webApplicationInfo.id`) and `identifier_uri` into
  `webApplicationInfo.resource`; package and upload to the org catalog; set `TEAMS_CATALOG_APP_ID` in `.env`.
- Set `APPROVERS_GROUP_ID` in `.env` to the approvers group's object id if `enable_group_check`.
- The messaging endpoint can be changed later with `terraform apply -var messaging_endpoint=…` or `az resource update`.

Not covered here (hosting-specific): the container platform, Key Vault / Secrets Manager for `bot.pfx`, and
Private Link for the Bot Service (see `docs/architecture-privatelink.html` for that design).
