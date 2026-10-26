$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create the virtual environment and install requirements first.' }
$taskLog = Join-Path $taskRoot 'watcher.log'
$taskErrorLog = Join-Path $taskRoot 'watcher_errors.log'
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList @('-u', 'main.py', '--watch') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput $taskLog -RedirectStandardError $taskErrorLog -PassThru
Set-Content -LiteralPath (Join-Path $taskRoot 'watcher.pid') -Value $taskProcess.Id
Write-Output "Watcher started (PID $($taskProcess.Id)). Put official files in test/bills and test/csv. Logs: watcher.log"
