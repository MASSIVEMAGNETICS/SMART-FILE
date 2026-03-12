; ============================================================================
; SMART-FILE — NSIS One-Click Windows Installer
; ============================================================================
;
; Build requirements:
;   • NSIS 3.x  (https://nsis.sourceforge.io)
;   • This file lives at:  installer/installer_script.nsi
;
; Build from the REPOSITORY ROOT directory (one level above installer/):
;   cd /path/to/SMART-FILE
;   makensis installer\installer_script.nsi
;
; All source-file paths are relative to the REPOSITORY ROOT.
; The resulting installer is written to:
;   SmartFile-Setup.exe   (in the repository root)
;
; Files included from the repository root:
;   main.py, add_context_menu.py, smart_organizer.py,
;   organize_v4.py, setup_integration.py, LICENSE, README.md
;   venv\   (optional — bundled if present at build time)
; ============================================================================

Unicode True

; ─── Metadata ────────────────────────────────────────────────────────────────
!define APP_NAME        "SMART-FILE"
!define APP_VERSION     "1.0.0"
!define APP_PUBLISHER   "MASSIVEMAGNETICS"
!define APP_URL         "https://github.com/MASSIVEMAGNETICS/SMART-FILE"
!define APP_EXEC        "main.py"
!define CONTEXT_SCRIPT  "add_context_menu.py"
!define UNINST_KEY      "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
!define REG_KEY         "Software\${APP_PUBLISHER}\${APP_NAME}"

; ─── Includes ────────────────────────────────────────────────────────────────
!include "MUI2.nsh"
!include "LogicLib.nsh"

; ─── Output & Permissions ────────────────────────────────────────────────────
Outfile "SmartFile-Setup.exe"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

; ─── Default install location ────────────────────────────────────────────────
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "${REG_KEY}" "InstallDir"

; ─── Branding ────────────────────────────────────────────────────────────────
Name "${APP_NAME} ${APP_VERSION}"
BrandingText "${APP_PUBLISHER} — ${APP_URL}"

; ─── MUI Settings ────────────────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ICON          "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON        "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP \
    "${NSISDIR}\Contrib\Graphics\Wizard\win.bmp"

; Header text for the welcome page
!define MUI_WELCOMEPAGE_TITLE   "Welcome to ${APP_NAME} Setup"
!define MUI_WELCOMEPAGE_TEXT    \
    "This wizard will install ${APP_NAME} ${APP_VERSION} on your computer.$\r$\n$\r$\n\
Right-click any folder in Windows Explorer to access:$\r$\n\
  • Smart Organize$\r$\n\
  • Undo Smart Organize$\r$\n$\r$\n\
Click Next to continue."

; Finish page — offer to launch the app
!define MUI_FINISHPAGE_RUN          "$INSTDIR\${APP_EXEC}"
!define MUI_FINISHPAGE_RUN_TEXT     "Launch SMART-FILE now"
!define MUI_FINISHPAGE_LINK         "Visit the project on GitHub"
!define MUI_FINISHPAGE_LINK_LOCATION "${APP_URL}"

; ─── Installer Pages ─────────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; ─── Uninstaller Pages ───────────────────────────────────────────────────────
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; ─── Language ────────────────────────────────────────────────────────────────
!insertmacro MUI_LANGUAGE "English"

; ─── Version Info ────────────────────────────────────────────────────────────
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductName"      "${APP_NAME}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductVersion"   "${APP_VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "CompanyName"      "${APP_PUBLISHER}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "LegalCopyright"   "© ${APP_PUBLISHER}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileDescription"  "${APP_NAME} Installer"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileVersion"      "${APP_VERSION}"

; ============================================================================
; Sections
; ============================================================================

; ─── Core Files (required) ───────────────────────────────────────────────────
Section "Core Application" SEC_CORE
    SectionIn RO   ; cannot be deselected

    SetOutPath "$INSTDIR"

    ; Copy the main Python scripts
    File "main.py"
    File "add_context_menu.py"
    File "smart_organizer.py"
    File "organize_v4.py"
    File "setup_integration.py"

    ; Copy LICENSE and README
    File /nonfatal "LICENSE"
    File /nonfatal "README.md"

    ; Copy the bundled virtual-environment (if present at build time)
    IfFileExists "venv\*.*" 0 +2
        File /r "venv"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Store install dir in registry
    WriteRegStr HKLM "${REG_KEY}" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "${REG_KEY}" "Version"    "${APP_VERSION}"

    ; Add entry to Windows "Apps & Features"
    WriteRegStr   HKLM "${UNINST_KEY}" "DisplayName"          "${APP_NAME}"
    WriteRegStr   HKLM "${UNINST_KEY}" "DisplayVersion"       "${APP_VERSION}"
    WriteRegStr   HKLM "${UNINST_KEY}" "Publisher"            "${APP_PUBLISHER}"
    WriteRegStr   HKLM "${UNINST_KEY}" "URLInfoAbout"         "${APP_URL}"
    WriteRegStr   HKLM "${UNINST_KEY}" "InstallLocation"      "$INSTDIR"
    WriteRegStr   HKLM "${UNINST_KEY}" "UninstallString"      '"$INSTDIR\Uninstall.exe"'
    WriteRegStr   HKLM "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify"             1
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair"             1

SectionEnd

; ─── Dependencies ────────────────────────────────────────────────────────────
Section "Install Python Dependencies" SEC_DEPS
    SectionIn 1

    ; Attempt to install optional dependencies via pip.
    ; The venv Python is preferred; fall back to system Python.
    IfFileExists "$INSTDIR\venv\Scripts\python.exe" 0 +3
        nsExec::ExecToLog '"$INSTDIR\venv\Scripts\python.exe" -m pip install tqdm rich'
        Goto deps_done

    ; Try system Python (python.exe must be on PATH)
    nsExec::ExecToLog 'python -m pip install tqdm rich'

    deps_done:
SectionEnd

; ─── Context Menu Integration ────────────────────────────────────────────────
Section "Add Windows Context Menu Entries" SEC_CTX

    DetailPrint "Adding Smart Organize context menu entries..."

    IfFileExists "$INSTDIR\venv\Scripts\python.exe" use_venv use_system

    use_venv:
        nsExec::ExecToLog '"$INSTDIR\venv\Scripts\python.exe" "$INSTDIR\${CONTEXT_SCRIPT}"'
        Goto ctx_done

    use_system:
        nsExec::ExecToLog 'python "$INSTDIR\${CONTEXT_SCRIPT}"'

    ctx_done:
        DetailPrint "Context menu entries installed."

SectionEnd

; ─── Desktop Shortcut ────────────────────────────────────────────────────────
Section "Create Desktop Shortcut" SEC_DESK

    ; Resolve the Python executable to use
    StrCpy $0 "python"
    IfFileExists "$INSTDIR\venv\Scripts\python.exe" 0 +2
        StrCpy $0 "$INSTDIR\venv\Scripts\python.exe"

    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" \
        "$0" \
        '"$INSTDIR\${APP_EXEC}" smart_organize' \
        "$INSTDIR\${APP_EXEC}" 0

SectionEnd

; ─── Start Menu Shortcuts ────────────────────────────────────────────────────
Section "Create Start Menu Shortcuts" SEC_SMENU

    StrCpy $0 "python"
    IfFileExists "$INSTDIR\venv\Scripts\python.exe" 0 +2
        StrCpy $0 "$INSTDIR\venv\Scripts\python.exe"

    CreateDirectory "$SMPROGRAMS\${APP_NAME}"

    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
        "$0" \
        '"$INSTDIR\${APP_EXEC}" smart_organize' \
        "$INSTDIR\${APP_EXEC}" 0

    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk" \
        "$INSTDIR\Uninstall.exe"

SectionEnd

; ─── Section Descriptions ────────────────────────────────────────────────────
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_CORE}  \
        "Core SMART-FILE scripts (required)."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DEPS}  \
        "Install optional Python packages (tqdm, rich) for an enhanced experience."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_CTX}   \
        "Add 'Smart Organize' and 'Undo Smart Organize' to the Windows right-click menu."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESK}  \
        "Add a shortcut to your Desktop."
    !insertmacro MUI_DESCRIPTION_TEXT ${SEC_SMENU} \
        "Add shortcuts to the Start Menu."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ============================================================================
; Uninstaller
; ============================================================================

Section "Uninstall"

    ; Remove context menu entries
    IfFileExists "$INSTDIR\${CONTEXT_SCRIPT}" 0 skip_ctx_removal
        IfFileExists "$INSTDIR\venv\Scripts\python.exe" 0 +3
            nsExec::ExecToLog '"$INSTDIR\venv\Scripts\python.exe" "$INSTDIR\${CONTEXT_SCRIPT}" --remove'
            Goto ctx_removed
        nsExec::ExecToLog 'python "$INSTDIR\${CONTEXT_SCRIPT}" --remove'
    ctx_removed:
    skip_ctx_removal:

    ; Remove installed files
    RMDir /r "$INSTDIR\venv"
    Delete "$INSTDIR\main.py"
    Delete "$INSTDIR\add_context_menu.py"
    Delete "$INSTDIR\smart_organizer.py"
    Delete "$INSTDIR\organize_v4.py"
    Delete "$INSTDIR\setup_integration.py"
    Delete "$INSTDIR\LICENSE"
    Delete "$INSTDIR\README.md"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir  "$INSTDIR"

    ; Remove shortcuts
    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk"
    RMDir  "$SMPROGRAMS\${APP_NAME}"

    ; Remove registry entries
    DeleteRegKey HKLM "${UNINST_KEY}"
    DeleteRegKey HKLM "${REG_KEY}"

SectionEnd
