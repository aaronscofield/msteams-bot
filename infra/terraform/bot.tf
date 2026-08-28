# ---- Azure Bot ------------------------------------------------------------------------------------
# The Azure Bot resource is a registration + channel router; it runs no code. It binds the Entra app id to
# the messaging endpoint and enables the Teams channel.

resource "azurerm_resource_group" "bot" {
  count    = var.create_resource_group ? 1 : 0
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

data "azurerm_resource_group" "bot" {
  count = var.create_resource_group ? 0 : 1
  name  = var.resource_group_name
}

locals {
  resource_group_name = var.create_resource_group ? azurerm_resource_group.bot[0].name : data.azurerm_resource_group.bot[0].name
}

resource "azurerm_bot_service_azure_bot" "bot" {
  name                = var.bot_name
  resource_group_name = local.resource_group_name
  location            = "global"
  sku                 = var.sku
  display_name        = var.bot_display_name

  microsoft_app_id        = azuread_application.bot.client_id
  microsoft_app_tenant_id = var.tenant_id
  microsoft_app_type      = "SingleTenant"

  endpoint = var.messaging_endpoint
  tags     = var.tags
}

resource "azurerm_bot_channel_ms_teams" "teams" {
  bot_name            = azurerm_bot_service_azure_bot.bot.name
  location            = azurerm_bot_service_azure_bot.bot.location
  resource_group_name = local.resource_group_name
}

# Teams SSO: the OAuth connection Bot Framework's token service uses to exchange the token Teams obtains for
# api://botid-<app> into a user token the bot can read.
resource "azurerm_bot_connection" "teams_sso" {
  count               = var.enable_teams_sso ? 1 : 0
  name                = var.sso_connection_name
  bot_name            = azurerm_bot_service_azure_bot.bot.name
  location            = azurerm_bot_service_azure_bot.bot.location
  resource_group_name = local.resource_group_name

  service_provider_name = "Aadv2Oauth2" # "Azure Active Directory v2"
  client_id             = azuread_application.bot.client_id
  client_secret         = azuread_application_password.sso[0].value
  scopes                = "api://botid-${azuread_application.bot.client_id}/access_as_user openid profile"

  parameters = {
    tenantID         = var.tenant_id
    tokenExchangeUrl = "api://botid-${azuread_application.bot.client_id}"
  }

  depends_on = [azuread_application_identifier_uri.bot, azuread_application_pre_authorized.teams]
}
