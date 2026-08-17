# Install Task Scheduler Autostart for Quantum AI Paper Bot
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c C:\Users\User\.gemini\antigravity-ide\scratch\quantum-ai-bot-main\ai-crypto-bot\START_BOT.bat"
$Trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "CryptoIntradayPaperBot" -Action $Action -Trigger $Trigger -Description "Quantum AI Paper Trading Bot Autostart"
Write-Host "Autostart Task 'CryptoIntradayPaperBot' Installed Successfully!" -ForegroundColor Green
