# Windows Task Scheduler (run once in PowerShell as the user who owns the repo).
# Machine clock must be IST. Edit $Repo and $Py.
$Repo = "C:\stock_data"
$Py   = "python"
$a1 = New-ScheduledTaskAction -Execute $Py -Argument "etl\bidask_recorder.py" -WorkingDirectory $Repo
$t1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 09:12
Register-ScheduledTask -TaskName "UpstoxBidAskRecorder" -Action $a1 -Trigger $t1 -Settings (New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 7) -StartWhenAvailable)
$a2 = New-ScheduledTaskAction -Execute $Py -Argument "etl\scheduler\compact_bidask.py" -WorkingDirectory $Repo
$t2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 15:50
Register-ScheduledTask -TaskName "UpstoxBidAskCompact" -Action $a2 -Trigger $t2
