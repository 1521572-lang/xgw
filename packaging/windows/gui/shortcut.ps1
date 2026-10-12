# Runs what the Start Menu shortcut runs (pythonw -I -m xgw panel --open) in an installed
# copy and reports what the person would see: the address handed to the browser, or
# the text of the message window (shortcut.log and shortcut-message.png in -Out).
#
#   powershell -ExecutionPolicy Bypass -File shortcut.ps1 -Home_Dir <Work>/XGW -Out <Work>
#
# -Redirected: the parent hands its output handles down, as some launchers do; the
# program is windowless all the same and must still report a failure in a window.
# Uses the same scratch registry keys and browser recorder as walk.ps1. ASCII only.
param(
    [Parameter(Mandatory = $true)][string]$Home_Dir,
    [Parameter(Mandatory = $true)][string]$Out,
    [switch]$Redirected
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class B {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern bool PostMessageW(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  public static string Text(IntPtr h) { var s = new StringBuilder(4096); GetWindowTextW(h, s, 4096); return s.ToString(); }
  public static string Class(IntPtr h) { var s = new StringBuilder(256); GetClassNameW(h, s, 256); return s.ToString(); }
  public static List<IntPtr> Boxes(uint pid) {
    var found = new List<IntPtr>();
    EnumWindows((h, l) => {
      uint owner; GetWindowThreadProcessId(h, out owner);
      if (owner == pid && IsWindowVisible(h) && Class(h) == "#32770") found.Add(h);
      return true;
    }, IntPtr.Zero);
    return found;
  }
  public static List<string> Texts(IntPtr box) {
    var found = new List<string>();
    EnumChildWindows(box, (h, l) => { var t = Text(h); if (t.Length > 0) found.Add(Class(h) + ": " + t); return true; }, IntPtr.Zero);
    return found;
  }
}
"@
[B]::SetProcessDPIAware() | Out-Null

$log = Join-Path $Out "shortcut.log"
function Say([string]$text) { Add-Content -Path $log -Value $text -Encoding UTF8 }
New-Item -ItemType Directory -Force $Out | Out-Null
$opened = Join-Path $Out "opened.txt"
Remove-Item $opened -ErrorAction SilentlyContinue
$env:XGW_WINPROXY_KEY = "Software\XGW-Test\gui\Internet Settings"
$env:XGW_WINRUN_KEY = "Software\XGW-Test\gui\Run"
$env:BROWSER = Join-Path $PSScriptRoot "browser.cmd"
$env:XGW_GUI_OPENED = $opened
foreach ($name in @("XGW_ROOT", "XGW_XRAY_BIN", "XGW_XRAY_SERVICE", "PYTHONPATH", "PYTHONHOME")) {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}

$pythonw = Join-Path $Home_Dir "app\python\pythonw.exe"
Say ("--- shortcut command" + $(if ($Redirected) { " (output handles redirected)" } else { "" }))
if ($Redirected) {
    # A parent that hands its own output handles down: the program is still windowless.
    $proc = Start-Process -FilePath $pythonw -ArgumentList "-I -m xgw panel --open" -PassThru `
        -RedirectStandardOutput (Join-Path $Out "stdout.txt") -RedirectStandardError (Join-Path $Out "stderr.txt")
} else {
    $proc = Start-Process -FilePath $pythonw -ArgumentList "-I -m xgw panel --open" -PassThru
}
$null = $proc.Handle
$deadline = [DateTime]::UtcNow.AddSeconds(40)
$seen = $false
while ([DateTime]::UtcNow -lt $deadline -and -not $proc.HasExited) {
    foreach ($h in [B]::Boxes([uint32]$proc.Id)) {
        Start-Sleep -Milliseconds 500
        Say ("message window, title: " + [B]::Text($h))
        foreach ($line in [B]::Texts($h)) { Say ("  " + ($line -replace "\r?\n", " / ")) }
        $r = New-Object B+RECT
        [B]::GetWindowRect($h, [ref]$r) | Out-Null
        $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $dc = $g.GetHdc()
        [B]::PrintWindow($h, $dc, 2) | Out-Null
        $g.ReleaseHdc($dc); $g.Dispose()
        $bmp.Save((Join-Path $Out "shortcut-message.png"), [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
        [B]::PostMessageW($h, 0x0111, [IntPtr]1, [IntPtr]::Zero) | Out-Null  # WM_COMMAND IDOK
        [B]::PostMessageW($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null  # WM_CLOSE
        $seen = $true
    }
    Start-Sleep -Milliseconds 300
}
if (-not $proc.HasExited) { $proc.WaitForExit(10000) | Out-Null }
if (-not $proc.HasExited) { Say "the command is still running - killing it"; $proc.Kill() }
Say ("exit code: " + $proc.ExitCode + "; message window shown: " + $seen)
if (Test-Path $opened) {
    Say ("browser was asked to open: " + ((Get-Content $opened -Raw).Trim() -replace "token=\S+", "token=<hidden>"))
} else {
    Say "browser was not asked to open anything"
}
