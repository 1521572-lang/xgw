; Установщик XGW для Windows (NSIS 3, Unicode). Собирается скриптом build.py — он
; готовит каталог STAGE (встроенный Python, код XGW, Xray, значок), рисует картинку
; первой и последней страниц (SIDE) и передаёт сюда их вместе с VERSION и OUTFILE.
;
; Встроенный Python везде запускается с -I: переменные PYTHON* из окружения
; пользователя на программу не влияют (иначе, например, PYTHONIOENCODING превращает
; русский текст в окне установки в кашу).
;
; Ставит программу в профиль пользователя (%LOCALAPPDATA%\XGW) без прав
; администратора: системный прокси и автозапуск — настройки самого пользователя.
; Всё, что не копирование файлов, делает сам XGW: `xgw winsetup install` после
; копирования и `xgw winsetup uninstall` перед удалением.
;
; Ключи для запуска без окон (проверки): /S — тихо; /NOSTART — не запускать демон и не
; включать автозапуск; /D=<каталог> — куда ставить (последним, без кавычек). У
; uninstall.exe: /S — тихо, /PURGE — стереть и настройки с подписками.

Unicode true
SetCompressor /SOLID lzma
RequestExecutionLevel user
ManifestDPIAware true

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "Sections.nsh"

!ifndef VERSION
  !error "не задан VERSION (сборку запускает packaging/windows/build.py)"
!endif
!ifndef STAGE
  !error "не задан STAGE"
!endif
!ifndef SIDE
  !error "не задан SIDE (картинка первой и последней страниц)"
!endif
!ifndef OUTFILE
  !error "не задан OUTFILE"
!endif

!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\XGW"
!define PYTHON "$INSTDIR\app\python\python.exe"
!define PYTHONW "$INSTDIR\app\python\pythonw.exe"

Name "XGW"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\XGW"
BrandingText "XGW ${VERSION}"
ShowInstDetails show
ShowUninstDetails show
SpaceTexts none  ; «требуется на диске» при удалении ни о чём не говорит

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1049 "ProductName" "XGW"
VIAddVersionKey /LANG=1049 "FileDescription" "Установка XGW — VPN-клиента на Xray-core"
VIAddVersionKey /LANG=1049 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1049 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1049 "LegalCopyright" "MIT; Python — PSF, Xray-core — MPL 2.0"

!define MUI_ICON "${STAGE}\xgw.ico"
!define MUI_UNICON "${STAGE}\xgw.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEFINISHPAGE_BITMAP "${SIDE}"

!define MUI_WELCOMEPAGE_TITLE "Установка XGW ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "XGW — VPN-клиент для этого компьютера: сам выбирает рабочий сервер из подписки и переключается, когда сервер «замораживают».$\r$\n$\r$\nПрограмма ставится в ваш профиль ($INSTDIR), права администратора не нужны. Настройки сети не меняются, пока вы не нажмёте кнопку включения VPN в панели управления.$\r$\n$\r$\nЕсли запущен другой VPN-клиент, лучше закрыть его: два VPN на одном компьютере мешают друг другу."
!insertmacro MUI_PAGE_WELCOME
; Заголовок страницы после копирования — из переменных: при сбое запуска XGW он не
; должен говорить «успешно».
Var DoneTitle
Var DoneText
!define MUI_INSTFILESPAGE_FINISHHEADER_TEXT "$DoneTitle"
!define MUI_INSTFILESPAGE_FINISHHEADER_SUBTEXT "$DoneText"
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "XGW установлен"
; С галочкой запуска места под текст мало: без этого определения он обрезается.
!define MUI_FINISHPAGE_TEXT_LARGE
!define MUI_FINISHPAGE_TEXT "XGW запущен и будет запускаться сам при входе в Windows.$\r$\n$\r$\nДальше — в панели управления: вставьте адрес подписки и нажмите большую кнопку.$\r$\n$\r$\nПанель открывается ярлыком «XGW» в меню «Пуск»."
!define MUI_FINISHPAGE_RUN "${PYTHONW}"
!define MUI_FINISHPAGE_RUN_PARAMETERS "-I -m xgw panel --open"
!define MUI_FINISHPAGE_RUN_TEXT "Открыть панель управления XGW"
!define MUI_PAGE_CUSTOMFUNCTION_SHOW FinishShow
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_COMPONENTS
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Russian"

Var NoStart
Var Failed  ; код, с которым XGW не настроился или не запустился; пусто — всё хорошо

Function .onInit
  StrCpy $NoStart ""
  StrCpy $Failed ""
  StrCpy $DoneTitle "Установка завершена"
  StrCpy $DoneText "XGW установлен."
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/NOSTART" $1
  ${IfNot} ${Errors}
    StrCpy $NoStart " --no-start --no-autostart"
  ${EndIf}
FunctionEnd

; Последняя страница не должна обещать того, чего не случилось.
Function FinishShow
  ${If} $Failed != ""
    SendMessage $mui.FinishPage.Title ${WM_SETTEXT} 0 "STR:XGW установлен, но не запущен"
    SendMessage $mui.FinishPage.Text ${WM_SETTEXT} 0 "STR:Файлы на месте, но XGW не запустился (код $Failed). Причина была в строках предыдущей страницы.$\r$\n$\r$\nЯрлык «XGW» в меню «Пуск» попробует запустить его ещё раз и откроет панель управления; не выйдет — покажет, что мешает."
  ${EndIf}
FunctionEnd

Section "XGW" SecMain
  SectionIn RO

  ; В каталог с чужими файлами не ставимся: удаление стёрло бы его подкаталог app.
  ; Свой каталог узнаётся по коду XGW (обновление) либо по настройкам, оставленным
  ; прошлым удалением (config, data).
  ${DirState} "$INSTDIR" $0
  ${If} $0 == 1
  ${AndIfNot} ${FileExists} "$INSTDIR\app\lib\xgw\__init__.py"
  ${AndIfNot} ${FileExists} "$INSTDIR\config\config.toml"
  ${AndIfNot} ${FileExists} "$INSTDIR\data\*.*"
    MessageBox MB_ICONSTOP "В каталоге $INSTDIR уже лежат другие файлы. XGW ставится только в пустой каталог." /SD IDOK
    SetErrorLevel 3
    Abort "каталог установки занят другими файлами"
  ${EndIf}

  ; Обновление: работающий XGW держит свои файлы открытыми.
  ${If} ${FileExists} "${PYTHON}"
    DetailPrint "Останавливаю работающий XGW…"
    nsExec::ExecToLog '"${PYTHON}" -I -m xgw stop'
    Pop $0
  ${EndIf}
  ; Прежний код убирается целиком: модули, которых в новой версии нет, не должны остаться.
  RMDir /r "$INSTDIR\app\lib"

  SetOutPath "$INSTDIR"
  File "${STAGE}\xgw.cmd"
  File "${STAGE}\xgw.ico"
  SetOutPath "$INSTDIR\licenses"
  File "${STAGE}\licenses\*.*"
  SetOutPath "$INSTDIR\app\python"
  File /r "${STAGE}\app\python\*.*"
  SetOutPath "$INSTDIR\app\lib"
  File /r "${STAGE}\app\lib\*.*"
  ; Xray, обновлённый командой `xgw update-xray`, более старым из установщика не заменяется.
  SetOutPath "$INSTDIR\app\xray"
  SetOverwrite ifnewer
  File "${STAGE}\app\xray\*.*"
  SetOverwrite on
  SetOutPath "$INSTDIR"

  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateShortcut "$SMPROGRAMS\XGW.lnk" "${PYTHONW}" "-I -m xgw panel --open" "$INSTDIR\xgw.ico" 0 SW_SHOWNORMAL "" "Панель управления XGW"

  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "XGW — VPN-клиент на Xray"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "XGW"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\xgw.ico"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR\app" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" "$0"

  ; Конфиг, токен панели, автозапуск и запуск демона — дело самого XGW.
  DetailPrint "Настраиваю и запускаю XGW…"
  nsExec::ExecToLog '"${PYTHON}" -I -m xgw winsetup install$NoStart'
  Pop $0
  ${If} $0 != 0
    DetailPrint "XGW сообщил об ошибке (код $0) — см. строки выше"
    SetErrorLevel 2
    StrCpy $Failed $0
    StrCpy $DoneTitle "XGW установлен, но не запущен"
    StrCpy $DoneText "Причина — в строках ниже."
    ; Окно остаётся на этой странице: строки с причиной должны быть видны.
    SetAutoClose false
    MessageBox MB_ICONEXCLAMATION "Файлы установлены, но XGW не запустился (код $0). Причина — в строках этого окна и в журнале $INSTDIR\data\logs\xgw.log." /SD IDOK
  ${EndIf}
SectionEnd

Section "un.XGW" UnMain
  SectionIn RO
  ; Остановить демон и Xray, вернуть системный прокси, убрать автозапуск.
  ${If} ${FileExists} "${PYTHON}"
    nsExec::ExecToLog '"${PYTHON}" -I -m xgw winsetup uninstall'
    Pop $0
    ${If} $0 != 0
      MessageBox MB_ICONEXCLAMATION|MB_YESNO "XGW не смог всё вернуть как было (код $0) — подробности в окне, кнопка «Детали». Проверьте прокси в «Параметры → Сеть и Интернет → Прокси-сервер».$\r$\n$\r$\nПродолжить удаление файлов?" /SD IDYES IDYES un_go_on
      Abort "удаление остановлено"
      un_go_on:
    ${EndIf}
  ${EndIf}
  Delete "$SMPROGRAMS\XGW.lnk"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\run"
  RMDir /r "$INSTDIR\licenses"
  Delete "$INSTDIR\xgw.cmd"
  Delete "$INSTDIR\xgw.ico"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"  ; только если пуст: настройки и подписки остаются для новой установки
  DeleteRegKey HKCU "${UNINST_KEY}"
SectionEnd

; Название короткое: список компонентов узкий, длинное обрезается.
Section /o "un.Настройки и подписки" UnData
  RMDir /r "$INSTDIR\config"
  RMDir /r "$INSTDIR\data"
  RMDir "$INSTDIR"
SectionEnd

Function un.onInit
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/PURGE" $1
  ${IfNot} ${Errors}
    !insertmacro SelectSection ${UnData}
  ${EndIf}
FunctionEnd

!insertmacro MUI_UNFUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${UnMain} "Программа XGW, встроенный Python, Xray, ярлык и автозапуск. Системный прокси возвращается к настройкам до XGW."
  !insertmacro MUI_DESCRIPTION_TEXT ${UnData} "Отметьте, чтобы стереть и подписки с настройками. Без отметки они останутся в папке XGW и подхватятся при новой установке."
!insertmacro MUI_UNFUNCTION_DESCRIPTION_END
