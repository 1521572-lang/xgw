@echo off
rem Stands in for the browser in the installer check: records the address it was asked to open.
>"%XGW_GUI_OPENED%" echo %*
