param(
    [string]$Registry = "sanfu.dockerhub.top",
    [string]$Project = "langgenius",
    [string]$Repository = "dify-api",
    [string]$Tag = "1.11.1-sanfu-log-20260529-3",
    [string]$Username = "ljq82"
)

$ErrorActionPreference = "Stop"

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
    [System.Environment]::GetEnvironmentVariable("Path", "User")

$image = "$Registry/$Project/$Repository`:$Tag"
$commitSha = (git rev-parse --short HEAD).Trim()
$dockerConfig = Join-Path ([System.IO.Path]::GetTempPath()) ("sanfu-docker-config-" + [guid]::NewGuid())

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker command was not found. Run this on a machine with Docker or a compatible Docker CLI."
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$ErrorMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $ErrorMessage
    }
}

if ($env:HARBOR_PASSWORD) {
    $password = $env:HARBOR_PASSWORD
} else {
    $securePassword = Read-Host "Harbor password" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    try {
        $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

try {
    New-Item -ItemType Directory -Force -Path $dockerConfig | Out-Null
    $env:DOCKER_CONFIG = $dockerConfig

    $password | docker login $Registry --username $Username --password-stdin
    if ($LASTEXITCODE -ne 0) {
        throw "Docker login failed for $Registry."
    }

    Invoke-NativeCommand {
        docker build --pull --build-arg COMMIT_SHA="$commitSha-sanfu-log" -f api/Dockerfile -t $image api
    } "Docker build failed for $image."

    Invoke-NativeCommand {
        docker push $image
    } "Docker push failed for $image."

    Write-Host "Pushed image: $image"
} finally {
    if (Test-Path $dockerConfig) {
        Remove-Item -LiteralPath $dockerConfig -Recurse -Force
    }
}
