# Remove Task Scheduler Autostart for Quantum AI Paper Bot
Unregister-ScheduledTask -TaskName "CryptoIntradayPaperBot" -Confirm:$false
Write-Host "Autostart Task 'CryptoIntradayPaperBot' Removed Successfully!" -ForegroundColor Yellow
