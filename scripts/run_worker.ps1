$ErrorActionPreference = "Stop"

$requiredVars = @("DATABASE_URL", "DEEPSEEK_API_KEY")
if (($env:DATASET_STORAGE_MODE -eq "supabase")) {
    $requiredVars += @("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_STORAGE_BUCKET")
}

$missing = @()
foreach ($name in $requiredVars) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        $missing += $name
    }
}

if ($missing.Count -gt 0) {
    Write-Error ("Missing required environment variables: " + ($missing -join ", "))
    exit 2
}

if ([string]::IsNullOrWhiteSpace($env:DATASET_STORAGE_MODE)) {
    $env:DATASET_STORAGE_MODE = "local"
}
if ([string]::IsNullOrWhiteSpace($env:WORKER_POLL_SECONDS)) {
    $env:WORKER_POLL_SECONDS = "5"
}

python -m src.worker
