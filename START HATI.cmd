@echo off
title HATI - Spectral Hound Launcher
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-hati.ps1"
