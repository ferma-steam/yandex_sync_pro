@echo off
echo ========================================
echo  Сборка Yandex Disk Sync Pro v2.5
echo ========================================
echo.

REM Проверка наличия PyInstaller
where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo ❌ PyInstaller не установлен. Установка...
    pip install pyinstaller pyinstaller-hooks-contrib
)

REM Сборка EXE файла
echo 📦 Сборка исполняемого файла...
pyinstaller ^
  --onefile ^
  --windowed ^
  --icon=assets\icon.ico ^
  --name=yandex_sync_pro ^
  --add-data "assets;assets" ^
  --hidden-import=ttkbootstrap ^
  --hidden-import=watchdog.observers ^
  --hidden-import=watchdog.events ^
  --hidden-import=pystray ^
  --hidden-import=PIL ^
  --hidden-import=cryptography.fernet ^
  --hidden-import=matplotlib.backends.backend_tkagg ^
  main.py

if errorlevel 1 (
    echo ❌ Ошибка сборки EXE
    pause
    exit /b 1
)

echo ✅ EXE собран успешно

REM Копирование ресурсов в папку dist
xcopy assets dist\assets\ /E /I /Y

REM Сборка инсталлятора через Inno Setup
echo.
echo 📦 Сборка инсталлятора...
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    "C:\Program Files\Inno Setup 6\ISCC.exe" installer.iss
) else (
    echo ⚠️  Inno Setup не найден. Скопируйте файлы вручную из папки dist
    pause
    exit /b 1
)

if errorlevel 1 (
    echo ❌ Ошибка сборки инсталлятора
    pause
    exit /b 1
)

echo.
echo ========================================
echo  ✅ Сборка завершена успешно!
echo  Инсталлятор: installer_output\yandex_disk_sync_pro_setup.exe
echo ========================================
pause