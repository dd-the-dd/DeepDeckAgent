param(
    [string]$Owner = "dd-the-dd",
    [string]$Repository = "DeepDeckAgent"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$rulesetPath = Join-Path $repositoryRoot ".github\rulesets\protect-main.json"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required. Install it, then run: gh auth login"
}

gh auth status | Out-Null
gh repo create "$Owner/$Repository" --public --source $repositoryRoot --remote origin --push
Get-Content -LiteralPath $rulesetPath -Raw |
    gh api --method POST "repos/$Owner/$Repository/rulesets" --input - | Out-Null

Write-Host "Published https://github.com/$Owner/$Repository with the owner-only main ruleset."
