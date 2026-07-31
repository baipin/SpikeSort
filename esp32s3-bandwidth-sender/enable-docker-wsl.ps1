$ErrorActionPreference = "Continue"
$logPath = Join-Path $PSScriptRoot "enable-docker-wsl.log"
Start-Transcript -Path $logPath -Force

Write-Host "Enabling Windows features required by Docker Desktop WSL2 backend..."
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
dism.exe /online /enable-feature /featurename:HypervisorPlatform /all /norestart

Write-Host "Setting hypervisor launch type to auto..."
bcdedit /set hypervisorlaunchtype auto

Write-Host "Installing/updating WSL core components without adding a Linux distro..."
wsl.exe --install --no-distribution
wsl.exe --update
wsl.exe --set-default-version 2

Write-Host "Current WSL status:"
wsl.exe --status

Write-Host "Done. A Windows restart is usually required before Docker Desktop can detect WSL2 virtualization."
Stop-Transcript
