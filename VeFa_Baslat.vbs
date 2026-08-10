Set WshShell = CreateObject("WScript.Shell")
' Run pythonw invisibly to completely hide the console
WshShell.Run "pythonw backend\VeFa_Tray.py", 0, False
