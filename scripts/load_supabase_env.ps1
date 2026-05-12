param(
    [string]$SecretsPath = ".streamlit/secrets.toml",
    [ValidateSet("smoke", "worker", "all")]
    [string]$Profile = "smoke",
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

function Get-TomlValue {
    param(
        [string[]]$Lines,
        [string]$Key
    )

    $pattern = '^\s*' + [Regex]::Escape($Key) + '\s*=\s*"(.*)"\s*$'
    foreach ($line in $Lines) {
        if ($line -match $pattern) {
            return $matches[1]
        }
    }
    return $null
}

function Set-SessionEnvVar {
    param(
        [string]$Name,
        [string]$Value
    )

    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        Set-Item -Path ("Env:" + $Name) -Value $Value
        if (-not $Quiet) {
            Write-Host ("Set " + $Name)
        }
    }
}

if (-not (Test-Path -LiteralPath $SecretsPath)) {
    Write-Error ("Secrets file not found: " + $SecretsPath)
    exit 1
}

$lines = Get-Content -LiteralPath $SecretsPath -Encoding UTF8

$mapping = [ordered]@{
    "database_url" = "DATABASE_URL"
    "agent_task_executor_mode" = "AGENT_TASK_EXECUTOR_MODE"
    "dataset_storage_mode" = "DATASET_STORAGE_MODE"
    "supabase_url" = "SUPABASE_URL"
    "supabase_service_role_key" = "SUPABASE_SERVICE_ROLE_KEY"
    "supabase_storage_bucket" = "SUPABASE_STORAGE_BUCKET"
    "deepseek_api_key" = "DEEPSEEK_API_KEY"
    "deepseek_model" = "DEEPSEEK_MODEL"
    "deepseek_base_url" = "DEEPSEEK_BASE_URL"
}

$selectedKeys = switch ($Profile) {
    "smoke" { @("database_url", "agent_task_executor_mode", "dataset_storage_mode", "supabase_url", "supabase_service_role_key", "supabase_storage_bucket") }
    "worker" { @("database_url", "agent_task_executor_mode", "dataset_storage_mode", "supabase_url", "supabase_service_role_key", "supabase_storage_bucket", "deepseek_api_key", "deepseek_model", "deepseek_base_url") }
    default { $mapping.Keys }
}

$missing = @()
foreach ($key in $selectedKeys) {
    $value = Get-TomlValue -Lines $lines -Key $key
    if ([string]::IsNullOrWhiteSpace($value)) {
        $missing += $key
        continue
    }
    Set-SessionEnvVar -Name $mapping[$key] -Value $value
}

if ($missing.Count -gt 0) {
    Write-Warning ("Missing or blank keys in secrets file: " + ($missing -join ", "))
}

if (-not $Quiet) {
    Write-Host ""
    Write-Host "Environment variables loaded into the current PowerShell session."
    Write-Host "Use this script with dot-sourcing so the variables stay available:"
    Write-Host (". .\scripts\load_supabase_env.ps1 -Profile " + $Profile)
}
