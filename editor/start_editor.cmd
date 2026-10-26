@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$editorRoot = '%~dp0'; try { $status = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2; if ($status.ok) { Start-Process 'http://127.0.0.1:8765/'; exit 0 } } catch {}; $pythonExe = (Get-Command python -ErrorAction Stop).Source; Start-Process -FilePath $pythonExe -ArgumentList @('server.py','--open') -WorkingDirectory $editorRoot -WindowStyle Hidden"
if errorlevel 1 (
 echo Failed to start editor. Run python server.py --open from this folder.
 pause
)


