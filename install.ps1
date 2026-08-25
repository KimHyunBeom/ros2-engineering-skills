[CmdletBinding()]
param(
    [string]$Target = (Join-Path $HOME '.agents/skills/ros2-engineering-skills'),
    [switch]$Link,
    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath($PSScriptRoot)
if ($Target.StartsWith('~')) {
    $Target = Join-Path $HOME $Target.Substring(1).TrimStart('/', '\')
}
$Target = [System.IO.Path]::GetFullPath($Target)
$HomePath = [System.IO.Path]::GetFullPath($HOME)
$PathRoot = [System.IO.Path]::GetPathRoot($Target)

if ($Target -eq $Root -or
    $Target.StartsWith(
        $Root + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    ) -or
    $Target -eq $HomePath -or $Target -eq $PathRoot) {
    throw "Refusing unsafe target: $Target"
}

$Exists = Test-Path -LiteralPath $Target
if ($Exists -and -not $Force) {
    throw "Target already exists: $Target (use -Force to replace it)"
}

$Mode = if ($Link) { 'link' } else { 'copy' }
if ($DryRun) {
    Write-Output "mode=$Mode"
    Write-Output "source=$Root"
    Write-Output "target=$Target"
    Write-Output "force=$($Force.IsPresent)"
    exit 0
}

if ($Exists) {
    Remove-Item -LiteralPath $Target -Recurse -Force
}
$Parent = Split-Path -Parent $Target
New-Item -ItemType Directory -Path $Parent -Force | Out-Null

if ($Link) {
    New-Item -ItemType SymbolicLink -Path $Target -Target $Root | Out-Null
}
else {
    New-Item -ItemType Directory -Path $Target -Force | Out-Null
    $Excluded = @(
        '.git', '.venv', 'venv', '__pycache__',
        '.pytest_cache', '.mypy_cache', '.coverage'
    )
    Get-ChildItem -LiteralPath $Root -Force |
        Where-Object { $Excluded -notcontains $_.Name } |
        Copy-Item -Destination $Target -Recurse -Force
}

$Skill = Join-Path $Target 'SKILL.md'
$References = Join-Path $Target 'references'
if (-not (Test-Path -LiteralPath $Skill -PathType Leaf)) {
    throw 'SKILL.md was not installed'
}
if (-not (Test-Path -LiteralPath $References -PathType Container)) {
    throw 'references/ was not installed'
}
if (-not (Select-String -LiteralPath $Skill -Pattern '^name: ros2-engineering-skills$' -Quiet)) {
    throw 'Installed SKILL.md has an unexpected name'
}

Write-Output "installed ros2-engineering-skills at $Target ($Mode)"
