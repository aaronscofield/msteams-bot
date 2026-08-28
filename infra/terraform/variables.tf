variable "subscription_id" {
  description = "Azure subscription that holds the Bot resource."
  type        = string
}

variable "tenant_id" {
  description = "Entra tenant id. The bot is SingleTenant: only tokens from this tenant are accepted."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group for the Azure Bot."
  type        = string
}

variable "create_resource_group" {
  description = "Create the resource group (true) or use an existing one (false)."
  type        = bool
  default     = false
}

variable "location" {
  description = "Region for the resource group if created. The Azure Bot itself is a global resource."
  type        = string
  default     = "eastus2"
}

variable "bot_name" {
  description = "Azure Bot resource name (globally unique) and the Entra app registration's display name."
  type        = string
}

variable "bot_display_name" {
  description = "Name shown in Azure and used as the Teams app's default display name."
  type        = string
  default     = "Company Approval Bot"
}

variable "sku" {
  description = "Azure Bot pricing tier: F0 (free) or S1."
  type        = string
  default     = "F0"
  validation {
    condition     = contains(["F0", "S1"], var.sku)
    error_message = "sku must be F0 or S1."
  }
}

variable "messaging_endpoint" {
  description = "Public HTTPS URL Bot Framework posts activities to: https://<host><route prefix>/messages."
  type        = string
}

variable "certificate_pem_path" {
  description = "Path to the bot's public certificate (PEM). Registered on the app registration; the bot signs client assertions with the matching private key (certs/bot.pfx)."
  type        = string
}

variable "certificate_end_date" {
  description = "Expiry of the certificate credential (RFC3339). Match the certificate's notAfter."
  type        = string
}

variable "enable_group_check" {
  description = "Grant GroupMember.Read.All so the bot can enforce APPROVERS_GROUP_ID."
  type        = bool
  default     = true
}

variable "enable_teams_sso" {
  description = "Expose api://botid-<app>/access_as_user, pre-authorise the Teams clients, and create the Azure Bot OAuth connection (needs a client secret, created here)."
  type        = bool
  default     = true
}

variable "sso_connection_name" {
  description = "Name of the Azure Bot OAuth connection; must match AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__SSO__SETTINGS__AZUREBOTOAUTHCONNECTIONNAME."
  type        = string
  default     = "teams-sso"
}

variable "tags" {
  description = "Tags applied to the Azure resources."
  type        = map(string)
  default     = {}
}

# Microsoft Teams first-party client ids that may obtain tokens for the bot's API without a consent prompt.
variable "teams_client_ids" {
  description = "Teams desktop/mobile and Teams web application ids (Microsoft first-party; do not change)."
  type        = list(string)
  default = [
    "1fec8e78-bce4-4aaf-ab1b-5451cc387264", # Teams desktop / mobile
    "5e3ce6c0-2b1f-4285-8d4b-75ee78787346", # Teams web
  ]
}
