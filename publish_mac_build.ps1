# Push to GitHub and trigger macOS build (run on Windows).
# Requires: git, GitHub account, repo created at github.com

param(
    [Parameter(Mandatory = $true)]
    [string]$RepoUrl   # e.g. https://github.com/user/alan-graham-video.git
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "Git is not installed."
}

if (-not (Test-Path ".git")) {
    git init
    git branch -M main
}

git add .gitignore .github gui.py image_zoom_reveal.py brush_stroke_reveal.py `
    requirements.txt build_requirements.txt build_mac.sh `
    alan_graham_video_editor_mac.spec pyi_rth_ffmpeg.py publish_mac_build.ps1

git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "Add macOS build workflow for Alan Graham Video Editor"
}

$remotes = @(git remote 2>$null)
if ($remotes -contains "origin") {
    git remote remove origin
}
git remote add origin $RepoUrl
git push -u origin main --force

Write-Host ""
Write-Host "Code pushed. Now on GitHub:"
Write-Host "  1. Open the repo → Actions tab"
Write-Host "  2. Run workflow 'Build macOS App' → Run workflow"
Write-Host "  3. When finished, download artifact: Alan-Graham-Video-Editor-macOS.zip"
Write-Host "  4. Send that zip to the Mac client (contains .app)"
Write-Host ""
