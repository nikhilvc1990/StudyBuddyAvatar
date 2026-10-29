@echo off
rem Launch StudyBuddyAvatar outside PyCharm. Run setup.bat once first.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
    goto :end
)

where conda >nul 2>nul
if %errorlevel%==0 (
    call conda run --no-capture-output -n studybuddy python main.py
    goto :end
)

for %%R in ("%USERPROFILE%\miniconda3" "%USERPROFILE%\anaconda3" "%LOCALAPPDATA%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%ProgramData%\miniconda3" "%ProgramData%\anaconda3") do (
    if exist "%%~R\envs\studybuddy\python.exe" (
        "%%~R\envs\studybuddy\python.exe" main.py
        goto :end
    )
)

echo Could not find the StudyBuddy environment. Run setup.bat first.

:end
if errorlevel 1 pause
