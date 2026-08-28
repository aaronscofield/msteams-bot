output "client_id" {
  description = "Entra app (client) id — CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID, and the Teams manifest's id / botId / webApplicationInfo.id."
  value       = azuread_application.bot.client_id
}

output "tenant_id" {
  value = var.tenant_id
}

output "bot_name" {
  value = azurerm_bot_service_azure_bot.bot.name
}

output "identifier_uri" {
  description = "webApplicationInfo.resource in the Teams manifest."
  value       = var.enable_teams_sso ? "api://botid-${azuread_application.bot.client_id}" : null
}

output "sso_connection_name" {
  value = var.enable_teams_sso ? azurerm_bot_connection.teams_sso[0].name : null
}

output "env_snippet" {
  description = "Lines for the bot's .env."
  value       = <<-EOT
    CONNECTIONS__SERVICE_CONNECTION__SETTINGS__AUTHTYPE=certificate
    CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID=${azuread_application.bot.client_id}
    CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID=${var.tenant_id}
    CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CERTPFXFILE=./certs/bot.pfx
    CONNECTIONS__SERVICE_CONNECTION__SETTINGS__VALIDATE_ISSUER=true
    CONNECTIONSMAP__0__SERVICEURL=*
    CONNECTIONSMAP__0__CONNECTION=SERVICE_CONNECTION
    ${var.enable_teams_sso ? "AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__SSO__TYPE=UserAuthorization\n    AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__SSO__SETTINGS__AZUREBOTOAUTHCONNECTIONNAME=${var.sso_connection_name}" : ""}
  EOT
}
