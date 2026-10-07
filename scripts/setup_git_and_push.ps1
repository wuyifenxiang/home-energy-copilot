#!/usr/bin/env pwsh
<#
.SYNOPSIS
    First-commit and push script for the Amazon Developer Hackathon 2026 project.

.DESCRIPTION
    Idempotent and safe to re-run:
      * creates the first commit if there is not one yet
      * verifies the remote URL is a GitHub repo URL that exists
      * pushes the branch to origin

    It never force-pushes, never rewrites history, and never touches any other repo.

.PARAMETER Email
    The email recorded in your git commit. Use your GitHub noreply address to keep
    your real address private:  <id>+<username>@users.noreply.github.com

.PARAMETER Name
    The name recorded in your git commit. Defaults to your GitHub username.

.PARAMETER RepoUrl
    The repository you created on GitHub. HTTPS or SSH both work.
    Example: https://github.com/yourname/home-energy-copilot.git

.EXAMPLE
    # 1) Set your identity for this repo, once
    ./scripts/setup_git_and_push.ps1 -Email you@example.com -Name yourname -RepoUrl https://github.com/yourname/home-energy-copilot.git -ConfigureIdentity

.EXAMPLE
    # 2) Commit and push
    ./scripts/setup_git_and_push.ps1 -Email you@example.com -Name yourname -RepoUrl https://github.com/yourname/home-energy-copilot.git
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Email,
    [string]$Name,
    [Parameter(Mandatory = $true)][string]$RepoUrl,
    [switch]$ConfigureIdentity
)

$ErrorActionPreference = 'Stop'

function Step($n, $text) { Write-Host "`n[$n] $text" -ForegroundColor Cyan }
function Ok($text)       { Write-Host "    OK   $text" -ForegroundColor Green }
function Warn($text)     { Write-Host "    WARN $text" -ForegroundColor Yellow }
function Die($text)      { Write-Host "`n    FAIL $text" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- sanity
Step 1 'Locating the repository'

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Die 'git is not on PATH.' }

# Resolve the repo root from this script's location, never from the caller's cwd.
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

if (-not (Test-Path (Join-Path $repoRoot '.git'))) {
    Die "No .git directory in $repoRoot. Run 'git init -b main' there first."
}
# Never operate on a parent repository by accident.
$parentGit = Join-Path (Split-Path -Parent $repoRoot) '.git'
if (Test-Path $parentGit) { Die "A parent directory is also a git repo ($parentGit). Refusing to continue." }

Ok "repo root: $repoRoot"

if (-not $Name) { $Name = 'GitHub User' }

# ------------------------------------------------------- identity check
Step 2 'Checking git identity'

if ($ConfigureIdentity) {
    git config user.email $Email
    if ($LASTEXITCODE -ne 0) { Die 'Could not set user.email.' }
    git config user.name $Name
    if ($LASTEXITCODE -ne 0) { Die 'Could not set user.name.' }
    Ok "set user.name='$Name' user.email='$Email' (this repo only)"
}

$cfgEmail = (git config user.email) 2>$null
$cfgName  = (git config user.name)  2>$null
if (-not $cfgEmail -or -not $cfgName) {
    Die @"
git identity is not configured and -ConfigureIdentity was not passed.
Re-run with -ConfigureIdentity, for example:

    ./scripts/setup_git_and_push.ps1 ``
        -Email $Email -Name $Name -RepoUrl $RepoUrl -ConfigureIdentity
"@
}
Ok "commit author will be: $cfgName <$cfgEmail>"

# --------------------------------------------------------- stage + commit
Step 3 'Staging and committing'

$staged = git diff --cached --name-only
if (-not $staged) {
    git add -A
    if ($LASTEXITCODE -ne 0) { Die 'git add failed.' }
}

# Guard against committing local state.
$junk = git diff --cached --name-only | Where-Object { $_ -match '\.db$|^data/|__pycache__|\.pyc$|\.env$' }
if ($junk) {
    Write-Host "    These files should not be committed:" -ForegroundColor Red
    $junk | ForEach-Object { Write-Host "      $_" }
    Die 'Refusing to commit database, cache, or secret files.'
}
Ok "$((git diff --cached --name-only | Measure-Object).Count) files staged, none of them state or secrets"

$hasCommit = $false
# Note: git writes "fatal: Needed a single revision" to stderr on a repo with no
# commits yet. With $ErrorActionPreference = 'Stop', PowerShell treats that native
# stderr output as a terminating error, so the failure MUST be caught rather than
# allowed to bubble up. This is why the call is wrapped instead of using a plain
# redirect.
try {
    git rev-parse --verify HEAD 2>$null | Out-Null
    $hasCommit = ($LASTEXITCODE -eq 0)
} catch {
    $hasCommit = $false
}

if (-not $hasCommit) {
    $message = @'
Initial commit: Home Energy Copilot, an Alexa+ MCP add-on

A self-hosted Model Context Protocol server for the Alexa+ track of the
Amazon Developer Hackathon 2026.

- Implements MCP revision 2025-11-25 over Streamable HTTP in the Python
  standard library, with zero runtime dependencies.
- Exposes seven voice-first tools for home energy questions and actions.
- Every state-changing tool is two-phase: propose, then confirm.
- 57-check end-to-end suite: python tests/smoke_test.py
- Friction log with reproducible evidence: friction-log/FRICTION_LOG.md
'@
    git commit -q -m $message
    if ($LASTEXITCODE -ne 0) { Die 'git commit failed.' }
    Ok 'created the first commit'
} else {
    if (git diff --cached --quiet) {
        Ok 'nothing to commit - the working tree is already committed'
    } else {
        git commit -q -m 'Update submission materials'
        if ($LASTEXITCODE -ne 0) { Die 'git commit failed.' }
        Ok 'committed pending changes'
    }
}

# ------------------------------------------------------------ remote
Step 4 'Configuring the remote'

if ($RepoUrl -notmatch '^https://github\.com/[\w.-]+/[\w.-]+(\.git)?$' -and
    $RepoUrl -notmatch '^git@github\.com:[\w.-]+/[\w.-]+(\.git)?$') {
    Die "That does not look like a GitHub repository URL: $RepoUrl"
}

$existing = (git remote) 2>$null
if ($existing -contains 'origin') {
    git remote set-url origin $RepoUrl
    Ok "origin updated -> $RepoUrl"
} else {
    git remote add origin $RepoUrl
    Ok "origin added -> $RepoUrl"
}

# Confirm the remote exists before pushing, so a typo fails with a clear message.
$probe = git ls-remote --heads origin 2>&1
if ($LASTEXITCODE -ne 0) {
    Warn 'Could not reach the remote. Check that:'
    Warn '  - you created the repository on GitHub'
    Warn '  - the URL has no typo'
    Warn "  - the repo name matches exactly: $RepoUrl"
    Warn '  - you are signed in (a browser or credential prompt may appear on push)'
} else {
    Ok 'remote is reachable'
}

# ------------------------------------------------------------ push
Step 5 'Pushing'

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
git push -u origin $branch
if ($LASTEXITCODE -ne 0) { Die 'git push failed. If this was the first push, sign in when prompted and re-run.' }
Ok "pushed $branch to origin"

# ------------------------------------------------------------ next steps
Write-Host "`n$('=' * 68)" -ForegroundColor Cyan
Write-Host ' Push complete. Two manual steps remain on GitHub:' -ForegroundColor Cyan
Write-Host "$('=' * 68)" -ForegroundColor Cyan
Write-Host @"

  1. Keep the repo PUBLIC
     Settings -> General -> Danger Zone -> Change visibility

  2. Put MIT in the About sidebar (the LICENSE file alone is NOT enough)
     Repo home -> right sidebar -> the gear icon next to "About"
       Description : Self-hosted MCP server for Alexa+ (Amazon Developer
                     Hackathon 2026). Seven voice-first home energy tools.
       Topics      : alexa mcp mcp-server streamable-http python smart-home
                     energy-monitoring hackathon
       License     : MIT License   <-- this is the step the rules ask for
     Save changes.

     Verify by opening the repo in a private window while logged out.
     You should see "MIT license" in the sidebar.

"@ -ForegroundColor Gray

Write-Host '  Judges will run this:' -ForegroundColor Cyan
Write-Host @"
    git clone $RepoUrl
    cd home-energy-copilot
    python -m alexa_mcp --describe
    python tests/smoke_test.py

"@ -ForegroundColor Gray
