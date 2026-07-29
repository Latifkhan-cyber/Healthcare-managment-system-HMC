param(
    [string]$Port = '8001',
    [string]$Host = '127.0.0.1'
)

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$pythonCandidates = @(
    (Join-Path $repoRoot '.venv/Scripts/python.exe'),
    (Join-Path $repoRoot 'venv/Scripts/python.exe')
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $python = $candidate
        break
    }
}

if (-not $python) {
    $python = 'python'
}

$bindAddress = "$Host:$Port"
$browserUrl = "http://127.0.0.1:$Port/"

Write-Host "Starting Healthcare Management System on $bindAddress..."
Start-Process -FilePath $python -ArgumentList 'backend/manage.py','runserver',$bindAddress -WorkingDirectory $repoRoot
Start-Sleep -Seconds 4
Start-Process $browserUrl
Write-Host "Opened browser at $browserUrl"
