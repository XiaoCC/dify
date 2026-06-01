param(
    [string]$Namespace = "dify",
    [string]$Image = "sanfu.dockerhub.top/langgenius/dify-api:1.11.1-sanfu-log-20260529-3",
    [string]$ConfigPatch = "k8s/sanfu-log-configmap-patch.yaml",
    [string]$LogDbPassword = $env:SANFU_LOG_DB_PASSWORD
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    throw "kubectl command was not found. Run this on a machine with Kubernetes access."
}

if (-not $LogDbPassword) {
    $securePassword = Read-Host "SANFU_LOG_DB_PASSWORD" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    try {
        $LogDbPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$encodedPassword = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($LogDbPassword))
$secretPatch = @{ data = @{ SANFU_LOG_DB_PASSWORD = $encodedPassword } } | ConvertTo-Json -Compress
kubectl -n $Namespace patch secret dify-secret --type merge -p $secretPatch

kubectl -n $Namespace patch configmap dify-config --type merge --patch-file $ConfigPatch

kubectl -n $Namespace set image deployment/dify-api api=$Image
kubectl -n $Namespace set image deployment/dify-worker worker=$Image
kubectl -n $Namespace set image deployment/dify-worker-beat worker-beat=$Image

kubectl -n $Namespace rollout status deployment/dify-api --timeout=10m
kubectl -n $Namespace rollout status deployment/dify-worker --timeout=10m
kubectl -n $Namespace rollout status deployment/dify-worker-beat --timeout=10m

kubectl -n $Namespace get pods -l app=dify-api -o wide
kubectl -n $Namespace get pods -l app=dify-worker -o wide
kubectl -n $Namespace get pods -l app=dify-worker-beat -o wide
