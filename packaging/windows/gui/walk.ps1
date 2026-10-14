# Walks the XGW installer / uninstaller windows the way a person would: reads the
# texts of every page, takes a picture of the installer window itself (not the
# screen) and presses the buttons. Silent runs (/S) skip the pages, so clipped texts,
# a wrong last page or a dead "open the panel" box show up only here.
#
#   powershell -ExecutionPolicy Bypass -File walk.ps1 -Phase install `
#       -Setup build\windows\XGW-Setup-0.1.1.exe -Work <empty scratch folder>
#   powershell -ExecutionPolicy Bypass -File walk.ps1 -Phase uninstall -Work <same> [-Purge]
#
# Result in <Work>: install.log / uninstall.log (page texts, UTF-8) and *.png, one
# picture per page; the program goes to <Work>\XGW. To see the "XGW did not start"
# pages, put a broken <Work>\XGW\config\config.toml there before the install phase.
#
# What it touches on the machine: the Start Menu shortcut and the "installed
# programs" entry (both removed by the uninstall phase). The system proxy and
# autostart stay untouched: the installed program gets scratch registry keys
# (HKCU\Software\XGW-Test\gui) through the environment, and a recorder (browser.cmd)
# stands in for the browser. Do not run it while a real XGW is installed.
#
# ASCII only: Windows PowerShell reads scripts without BOM as ANSI.
param(
    [Parameter(Mandatory = $true)][ValidateSet("install", "uninstall")][string]$Phase,
    [Parameter(Mandatory = $true)][string]$Work,
    [string]$Setup = "",
    [string]$Switches = "",
    [switch]$Purge
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class W {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern IntPtr GetDlgItem(IntPtr h, int id);
  [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc p, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessageW(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern bool PostMessageW(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  public static List<IntPtr> Windows(uint pid) {
    var found = new List<IntPtr>();
    EnumWindows((h, l) => {
      uint owner; GetWindowThreadProcessId(h, out owner);
      if (owner == pid && IsWindowVisible(h)) found.Add(h);
      return true;
    }, IntPtr.Zero);
    return found;
  }
  public static IntPtr Child(IntPtr parent, string cls) {
    IntPtr found = IntPtr.Zero;
    EnumChildWindows(parent, (h, l) => {
      if (Class(h) == cls && IsWindowVisible(h)) { found = h; return false; }
      return true;
    }, IntPtr.Zero);
    return found;
  }
  public static string Text(IntPtr h) { var s = new StringBuilder(1024); GetWindowTextW(h, s, 1024); return s.ToString(); }
  public static string Class(IntPtr h) { var s = new StringBuilder(256); GetClassNameW(h, s, 256); return s.ToString(); }
}
"@
[W]::SetProcessDPIAware() | Out-Null

$log = Join-Path $Work "$Phase.log"
function Say([string]$text) { Add-Content -Path $log -Value $text -Encoding UTF8 }

function Shot([IntPtr]$h, [string]$name) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($h, [ref]$r) | Out-Null
    $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $dc = $g.GetHdc()
    [W]::PrintWindow($h, $dc, 2) | Out-Null
    $g.ReleaseHdc($dc); $g.Dispose()
    $bmp.Save((Join-Path $Work "$Phase-$name.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

function Dump([IntPtr]$h, [string]$title) {
    Say "--- $title"
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
    $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                         [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($e in $all) {
        $name = $e.Current.Name
        if (-not $name) { continue }
        $type = $e.Current.ControlType.ProgrammaticName -replace "ControlType\.", ""
        $extra = ""
        $pattern = $null
        if ($e.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) {
            $extra = " <" + $pattern.Current.ToggleState + ">"
        }
        if (-not $e.Current.IsEnabled) { $extra += " <disabled>" }
        Say ("  [$type] " + ($name -replace "\r?\n", " / ") + $extra)
    }
}

function Wait-Until([scriptblock]$check, [double]$seconds, [string]$what) {
    $deadline = [DateTime]::UtcNow.AddSeconds($seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (& $check) { return }
        Start-Sleep -Milliseconds 300
    }
    throw "timeout: $what"
}

function Main-Window($proc) {
    $script:main = [IntPtr]::Zero
    Wait-Until {
        foreach ($h in [W]::Windows([uint32]$proc.Id)) {
            if ([W]::Class($h) -eq "#32770" -and [W]::GetDlgItem($h, 1) -ne [IntPtr]::Zero) {
                $script:main = $h; return $true
            }
        }
        return $false
    } 60 "installer window"
    return $script:main
}

# Message boxes of the installer: report their text and close them.
function Boxes($proc, [IntPtr]$main) {
    foreach ($h in [W]::Windows([uint32]$proc.Id)) {
        if ($h -ne $main -and [W]::Class($h) -eq "#32770") {
            Dump $h ("message box: " + [W]::Text($h))
            Shot $h ("box-" + [DateTime]::UtcNow.Ticks)
            [W]::PostMessageW($h, 0x0111, [IntPtr]1, [IntPtr]::Zero) | Out-Null  # WM_COMMAND IDOK
            [W]::PostMessageW($h, 0x0111, [IntPtr]6, [IntPtr]::Zero) | Out-Null  # IDYES
            Start-Sleep -Milliseconds 500
        }
    }
}

# WM_COMMAND to the dialog itself: BM_CLICK is ignored while the window is not active
# (for example, right after a message box of the installer was closed).
function Press([IntPtr]$main, [int]$id) {
    [W]::PostMessageW($main, 0x0111, [IntPtr]$id, [W]::GetDlgItem($main, $id)) | Out-Null
}

function Next-Text([IntPtr]$main) { return [W]::Text([W]::GetDlgItem($main, 1)) }

New-Item -ItemType Directory -Force $Work | Out-Null
Remove-Item $log -ErrorAction SilentlyContinue
$home_dir = Join-Path $Work "XGW"
$env:XGW_WINPROXY_KEY = "Software\XGW-Test\gui\Internet Settings"
$env:XGW_WINRUN_KEY = "Software\XGW-Test\gui\Run"
$env:BROWSER = Join-Path $PSScriptRoot "browser.cmd"
$env:XGW_GUI_OPENED = Join-Path $Work "opened.txt"
foreach ($name in @("XGW_ROOT", "XGW_XRAY_BIN", "XGW_XRAY_SERVICE", "PYTHONPATH", "PYTHONHOME")) {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}

if ($Phase -eq "install") {
    if (-not $Setup) { throw "-Setup is required for the install phase" }
    if (Test-Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\XGW") {
        throw "XGW is already installed on this machine: the walk would disturb it"
    }
    Remove-Item $env:XGW_GUI_OPENED -ErrorAction SilentlyContinue
    $arguments = (($Switches + " /D=$home_dir").Trim())
    $proc = Start-Process -FilePath $Setup -ArgumentList $arguments -PassThru
    $null = $proc.Handle  # keeps the exit code readable after the process is gone
    $main = Main-Window $proc
    Start-Sleep -Milliseconds 800
    Say ("window title: " + [W]::Text($main))
    Dump $main "page 1 (welcome)"
    Shot $main "1-welcome"
    Press $main 1

    # Files page: the Next button is disabled while files are copied and XGW starts.
    Start-Sleep -Seconds 2
    Shot $main "2-files-running"
    $start = [DateTime]::UtcNow
    $script:before = Next-Text $main
    Wait-Until {
        Boxes $proc $main
        if ($proc.HasExited) { return $true }
        $next = [W]::GetDlgItem($main, 1)
        return [W]::IsWindowEnabled($next) -and ((Next-Text $main) -ne $script:before -or
            ([DateTime]::UtcNow - $start).TotalSeconds -gt 5)
    } 240 "installation to finish"
    Say ("installation took " + [int]([DateTime]::UtcNow - $start).TotalSeconds + " s")
    if ($proc.HasExited) { Say ("installer exited early, code " + $proc.ExitCode); exit 1 }
    Start-Sleep -Milliseconds 800
    Dump $main "page after installation"
    Shot $main "3-after-files"
    if ([W]::GetDlgItem($main, 1) -ne [IntPtr]::Zero -and (Next-Text $main)) {
        Say ("pressing: " + (Next-Text $main))
        Press $main 1
        Start-Sleep -Seconds 2
        if (-not $proc.HasExited) {
            Dump $main "next page"
            Shot $main "4-next"
            Say ("pressing: " + (Next-Text $main))
            Press $main 1
        }
    }
    $proc.WaitForExit(60000) | Out-Null
    Say ("installer exit code: " + $proc.ExitCode)
    # The finish page starts `pythonw -m xgw panel --open`; the browser is a recorder.
    # When that command fails it has no console: it must say so in a window of its own.
    $deadline = [DateTime]::UtcNow.AddSeconds(25)
    $seen = $false
    while ([DateTime]::UtcNow -lt $deadline -and -not $seen -and -not (Test-Path $env:XGW_GUI_OPENED)) {
        foreach ($candidate in (Get-Process pythonw -ErrorAction SilentlyContinue)) {
            $path = ""
            try { $path = $candidate.Path } catch { }
            if (-not $path -or -not $path.StartsWith($home_dir, [StringComparison]::OrdinalIgnoreCase)) { continue }
            foreach ($h in [W]::Windows([uint32]$candidate.Id)) {
                if ([W]::Class($h) -eq "#32770") {
                    Start-Sleep -Milliseconds 500
                    Dump $h ("window of the shortcut command: " + [W]::Text($h))
                    Shot $h "5-shortcut-message"
                    [W]::PostMessageW($h, 0x0111, [IntPtr]1, [IntPtr]::Zero) | Out-Null  # WM_COMMAND IDOK
                    [W]::PostMessageW($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # WM_CLOSE
                    $seen = $true
                }
            }
        }
        Start-Sleep -Milliseconds 400
    }
    if ($seen) { Say "the shortcut command reported its failure in a window" }
    try {
        Wait-Until { Test-Path $env:XGW_GUI_OPENED } 5 "panel address"
        Say ("browser was asked to open: " + ((Get-Content $env:XGW_GUI_OPENED -Raw) -replace "token=\S+", "token=<hidden>"))
    } catch {
        Say "browser was NOT asked to open anything"
    }
} else {
    $uninstaller = Join-Path $home_dir "uninstall.exe"
    $proc = Start-Process -FilePath $uninstaller -ArgumentList "_?=$home_dir" -PassThru
    $main = Main-Window $proc
    Start-Sleep -Milliseconds 800
    Say ("window title: " + [W]::Text($main))
    Dump $main "page 1 (confirm)"
    Shot $main "1-confirm"
    Press $main 1
    Start-Sleep -Seconds 1
    Dump $main "page 2 (components)"
    Shot $main "2-components"
    if ($Purge) {
        # Second item of the list: settings and subscriptions. The installer switches
        # a check box of its tree view on the space key.
        $tree = [W]::Child($main, "SysTreeView32")
        $first = [W]::SendMessageW($tree, 0x110A, [IntPtr]0, [IntPtr]::Zero)   # TVM_GETNEXTITEM, TVGN_ROOT
        $second = [W]::SendMessageW($tree, 0x110A, [IntPtr]1, $first)          # TVGN_NEXT
        Say ("tree view found: " + ($tree -ne [IntPtr]::Zero) + ", second item found: " + ($second -ne [IntPtr]::Zero))
        [W]::SendMessageW($tree, 0x110B, [IntPtr]9, $second) | Out-Null        # TVM_SELECTITEM, TVGN_CARET
        [W]::PostMessageW($tree, 0x0102, [IntPtr]0x20, [IntPtr]::Zero) | Out-Null  # WM_CHAR, space
        Start-Sleep -Milliseconds 800
        Shot $main "2-components-purge"
    }
    Say ("pressing: " + (Next-Text $main))
    Press $main 1
    $start = [DateTime]::UtcNow
    Start-Sleep -Seconds 2
    Wait-Until {
        Boxes $proc $main
        if ($proc.HasExited) { return $true }
        return [W]::IsWindowEnabled([W]::GetDlgItem($main, 1))
    } 180 "removal to finish"
    Say ("removal took " + [int]([DateTime]::UtcNow - $start).TotalSeconds + " s")
    if (-not $proc.HasExited) {
        Start-Sleep -Milliseconds 800
        Dump $main "page 3 (done)"
        Shot $main "3-done"
        Say ("pressing: " + (Next-Text $main))
        Press $main 1
        $proc.WaitForExit(30000) | Out-Null
    }
    Say ("uninstaller exit code: " + $proc.ExitCode)
}
