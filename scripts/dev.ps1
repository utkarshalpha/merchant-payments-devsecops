param([ValidateSet('Info','Build','Run')][string]$Action = 'Info')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$oldLocation = Get-Location
$previousJava = $env:JAVA_HOME
$previousPath = $env:PATH
try {
    Set-Location -LiteralPath $projectRoot
    $maven = Get-ChildItem -LiteralPath '.tools' -Directory -Filter 'apache-maven-*' | Select-Object -First 1
    if (-not $maven) { throw 'Project-local Maven has not been prepared under .tools.' }
    if (Test-Path -LiteralPath 'C:\Program Files\Java\jdk-25\bin\javac.exe') {
        $env:JAVA_HOME = 'C:\Program Files\Java\jdk-25'
    } elseif (-not $env:JAVA_HOME) {
        throw 'Set JAVA_HOME to a supported JDK 21 or 25 installation.'
    }
    $env:PATH = "$env:JAVA_HOME\bin;$($maven.FullName)\bin;$previousPath"
    $mavenCommand = Join-Path $maven.FullName 'bin/mvn.cmd'
    if ($Action -eq 'Info') {
        & $mavenCommand --version
    } elseif ($Action -eq 'Build') {
        & $mavenCommand --batch-mode --no-transfer-progress '-Dmaven.repo.local=.m2/repository' clean verify
    } else {
        if (-not (Test-Path -LiteralPath 'target/merchant-payments.jar')) { throw 'Run -Action Build first.' }
        if (-not $env:PAYMENTS_API_KEY) {
            $bytes = New-Object byte[] 32
            $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
            try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
            $env:PAYMENTS_API_KEY = [Convert]::ToBase64String($bytes)
        }
        Write-Host 'Starting http://127.0.0.1:8081. API key is in this terminal environment; it is not printed.'
        & (Join-Path $env:JAVA_HOME 'bin/java.exe') -jar target/merchant-payments.jar
    }
    if ($LASTEXITCODE -ne 0) { throw "Action $Action failed; inspect the first error above." }
} finally {
    $env:JAVA_HOME = $previousJava
    $env:PATH = $previousPath
    Set-Location -LiteralPath $oldLocation
}
