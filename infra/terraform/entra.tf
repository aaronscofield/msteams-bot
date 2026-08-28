# ---- Entra app registration: the bot's identity --------------------------------------------------
# One SingleTenant app registration is the bot's identity everywhere: Bot Framework validates inbound tokens
# against its client id, the bot signs app-only token requests with the certificate registered here, Graph
# permissions are granted to it, and (for Teams SSO) it exposes the API Teams obtains user tokens for.

data "azuread_client_config" "current" {}

data "azuread_application_published_app_ids" "well_known" {}

data "azuread_service_principal" "msgraph" {
  client_id = data.azuread_application_published_app_ids.well_known.result["MicrosoftGraph"]
}

locals {
  # Application permissions the bot uses (app-only, with the certificate).
  graph_app_roles = concat(
    ["TeamsAppInstallation.ReadWriteSelfForUser.All"], # install itself for users, find the 1:1 chat
    var.enable_group_check ? ["GroupMember.Read.All"] : [],
  )
}

resource "random_uuid" "access_as_user_scope" {}

resource "azuread_application" "bot" {
  display_name     = var.bot_name
  sign_in_audience = "AzureADMyOrg"
  owners           = [data.azuread_client_config.current.object_id]

  # Bot Framework's token service performs the OAuth redirect for the bot's OAuth connections (Test Connection,
  # non-silent sign-in). Without it Entra answers AADSTS500113.
  web {
    redirect_uris = ["https://token.botframework.com/.auth/web/redirect"]
  }

  api {
    requested_access_token_version = 2

    dynamic "oauth2_permission_scope" {
      for_each = var.enable_teams_sso ? [1] : []
      content {
        id                         = random_uuid.access_as_user_scope.result
        value                      = "access_as_user"
        type                       = "User"
        enabled                    = true
        admin_consent_display_name = "Access the approval bot as the signed-in user"
        admin_consent_description  = "Allows Microsoft Teams to obtain a token for the approval bot on behalf of the signed-in user, so the bot can verify who approved or rejected a request. Used only to confirm identity."
        user_consent_display_name  = "Verify your identity with the approval bot"
        user_consent_description   = "Lets the approval bot confirm it is you approving or rejecting a request in Teams."
      }
    }
  }

  # Declared Graph application permissions (consent is granted below via app role assignments).
  required_resource_access {
    resource_app_id = data.azuread_application_published_app_ids.well_known.result["MicrosoftGraph"]

    dynamic "resource_access" {
      for_each = local.graph_app_roles
      content {
        id   = data.azuread_service_principal.msgraph.app_role_ids[resource_access.value]
        type = "Role"
      }
    }
  }

  lifecycle {
    # identifier_uris is managed by azuread_application_identifier_uri (it needs the client id, which is only known after creation)
    ignore_changes = [identifier_uris]
  }
}

# api://botid-<client id> — must equal webApplicationInfo.resource in the Teams manifest and the OAuth
# connection's Token Exchange URL.
resource "azuread_application_identifier_uri" "bot" {
  count          = var.enable_teams_sso ? 1 : 0
  application_id = azuread_application.bot.id
  identifier_uri = "api://botid-${azuread_application.bot.client_id}"
}

# Pre-authorise the Teams clients for the scope → the SSO token exchange is silent (no consent prompt).
resource "azuread_application_pre_authorized" "teams" {
  for_each             = var.enable_teams_sso ? toset(var.teams_client_ids) : toset([])
  application_id       = azuread_application.bot.id
  authorized_client_id = each.value
  permission_ids       = [random_uuid.access_as_user_scope.result]
}

# The bot's credential: the public certificate. The private key never leaves the bot host (certs/bot.pfx).
resource "azuread_application_certificate" "bot" {
  application_id = azuread_application.bot.id
  type           = "AsymmetricX509Cert"
  encoding       = "pem"
  value          = file(var.certificate_pem_path)
  end_date       = var.certificate_end_date
}

# Azure Bot OAuth connections only support client secrets; this one is used solely by Bot Framework's token
# service to redeem Teams SSO tokens. Rotate by tainting.
resource "azuread_application_password" "sso" {
  count          = var.enable_teams_sso ? 1 : 0
  application_id = azuread_application.bot.id
  display_name   = "${var.sso_connection_name} oauth connection"
  end_date       = var.certificate_end_date
}

resource "azuread_service_principal" "bot" {
  client_id                    = azuread_application.bot.client_id
  app_role_assignment_required = false
  owners                       = [data.azuread_client_config.current.object_id]
}

# Admin consent for the Graph application permissions.
resource "azuread_app_role_assignment" "graph" {
  for_each            = toset(local.graph_app_roles)
  app_role_id         = data.azuread_service_principal.msgraph.app_role_ids[each.value]
  principal_object_id = azuread_service_principal.bot.object_id
  resource_object_id  = data.azuread_service_principal.msgraph.object_id
}
