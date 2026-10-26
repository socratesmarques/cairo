"""Windows window identities, monitor inventory and measured placement."""
import ctypes
import re
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WindowTarget:
    label: str
    executable: str = ""
    app_id: str = ""
    hwnd: int = 0
    pid: int = 0


class MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]


class Windows:
    def __init__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.window_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.monitor_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
        signatures = [
            (self.user.EnumWindows, [self.window_callback, wintypes.LPARAM], wintypes.BOOL),
            (self.user.EnumChildWindows, [wintypes.HWND, self.window_callback, wintypes.LPARAM], wintypes.BOOL),
            (self.user.IsWindowVisible, [wintypes.HWND], wintypes.BOOL),
            (self.user.IsZoomed, [wintypes.HWND], wintypes.BOOL),
            (self.user.GetForegroundWindow, [], wintypes.HWND),
            (self.user.GetClassNameW, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            (self.user.GetWindowThreadProcessId, [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            (self.kernel.OpenProcess, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            (self.kernel.QueryFullProcessImageNameW, [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            (self.kernel.GetApplicationUserModelId, [wintypes.HANDLE, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR], wintypes.LONG),
            (self.kernel.CloseHandle, [wintypes.HANDLE], wintypes.BOOL),
            (self.user.ShowWindow, [wintypes.HWND, ctypes.c_int], wintypes.BOOL),
            (self.user.SetForegroundWindow, [wintypes.HWND], wintypes.BOOL),
            (self.user.MonitorFromWindow, [wintypes.HWND, wintypes.DWORD], wintypes.HANDLE),
            (self.user.EnumDisplayMonitors, [wintypes.HDC, ctypes.POINTER(wintypes.RECT), self.monitor_callback, wintypes.LPARAM], wintypes.BOOL),
            (self.user.GetMonitorInfoW, [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)], wintypes.BOOL),
            (self.user.SetWindowPos, [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
            (self.user.GetWindowRect, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
        ]
        for function, args, result in signatures:
            function.argtypes, function.restype = args, result
        self.dpi_previous = None
        try:
            self.user.SetThreadDpiAwarenessContext.argtypes = [wintypes.HANDLE]
            self.user.SetThreadDpiAwarenessContext.restype = wintypes.HANDLE
            self.dpi_previous = self.user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        except AttributeError:
            pass
        self.com = None
        try:
            import pythoncom
            pythoncom.CoInitialize()
            self.com = pythoncom
        except ImportError:
            pass

    def close(self):
        if self.com:
            self.com.CoUninitialize()
        if self.dpi_previous:
            self.user.SetThreadDpiAwarenessContext(self.dpi_previous)

    def pid(self, hwnd):
        result = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(result))
        return result.value

    def identity_matches(self, hwnd, target):
        path, app_id = "", ""
        handle = self.kernel.OpenProcess(0x1000, False, self.pid(hwnd))
        if handle:
            try:
                size = wintypes.DWORD(32768)
                buffer = ctypes.create_unicode_buffer(size.value)
                if self.kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                    path = buffer.value
                length = wintypes.UINT(0)
                if target.app_id and self.kernel.GetApplicationUserModelId(handle, ctypes.byref(length), None) == 122 and 0 < length.value <= 32768:
                    value = ctypes.create_unicode_buffer(length.value)
                    if self.kernel.GetApplicationUserModelId(handle, ctypes.byref(length), value) == 0:
                        app_id = value.value
            finally:
                self.kernel.CloseHandle(handle)
        if target.executable and path.casefold() == target.executable.casefold():
            return True
        if target.executable and path:
            actual, expected = Path(path), Path(target.executable)
            # Squirrel's launcher and its versioned application process share one installation root.
            if actual.name.casefold() == expected.name.casefold() and actual.parent.parent == expected.parent and re.fullmatch(r"app-\d+(?:\.\d+){1,3}", actual.parent.name):
                return True
        if target.app_id:
            if app_id.casefold() == target.app_id.casefold():
                return True
            if self.com:
                try:
                    from win32com.propsys import propsys, pscon
                    store = propsys.SHGetPropertyStoreForWindow(hwnd, propsys.IID_IPropertyStore)
                    value = store.GetValue(pscon.PKEY_AppUserModel_ID)
                    value = value.GetValue() if hasattr(value, "GetValue") else value
                    if isinstance(value, str) and value.casefold() == target.app_id.casefold():
                        return True
                except Exception:
                    pass  # Unsupported property stores are not evidence of identity.
        return False

    def find(self, target):
        if target.hwnd:
            if not self.user.IsWindowVisible(target.hwnd) or self.pid(target.hwnd) != target.pid:
                raise ValueError("A janela mudou ou não está disponível; liste as janelas novamente")
            return target.hwnd
        matches, visited = [], [0]

        @self.window_callback
        def visit(hwnd, _):
            visited[0] += 1
            if visited[0] > 512 or not self.user.IsWindowVisible(hwnd):
                return True
            matched = self.identity_matches(hwnd, target)
            name = ctypes.create_unicode_buffer(128)
            self.user.GetClassNameW(hwnd, name, 128)
            if not matched and target.app_id and name.value == "ApplicationFrameWindow":
                children = [0]
                @self.window_callback
                def child(item, _):
                    children[0] += 1
                    if children[0] <= 64 and self.identity_matches(item, target):
                        matches.append(hwnd)
                    return True
                self.user.EnumChildWindows(hwnd, child, 0)
            elif matched:
                matches.append(hwnd)
            return True

        if not self.user.EnumWindows(visit, 0):
            raise OSError("Não foi possível consultar as janelas do Windows")
        foreground = self.user.GetForegroundWindow()
        return foreground if foreground in matches else matches[0] if matches else None

    def monitors(self):
        result = []
        @self.monitor_callback
        def visit(handle, _dc, _rect, _data):
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(info)
            if len(result) < 32 and self.user.GetMonitorInfoW(handle, ctypes.byref(info)):
                work, full = info.rcWork, info.rcMonitor
                result.append({"handle": handle, "device": info.szDevice, "primary": bool(info.dwFlags & 1),
                    "work": [work.left, work.top, work.right, work.bottom],
                    "bounds": [full.left, full.top, full.right, full.bottom]})
            return True
        if not self.user.EnumDisplayMonitors(None, None, visit, 0) or not result:
            raise OSError("Não consegui consultar os monitores conectados")
        result.sort(key=lambda item: (not item["primary"], item["work"][1], item["work"][0], item["device"]))
        return [{**item, "id": index} for index, item in enumerate(result, 1)]

    def monitor_for(self, hwnd):
        return self.user.MonitorFromWindow(hwnd, 2)

    def bounds(self, hwnd):
        rect = wintypes.RECT()
        if not self.user.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise OSError("Não consegui verificar a posição da janela")
        return rect.left, rect.top, rect.right, rect.bottom

    def move(self, hwnd, rect):
        if not self.user.SetWindowPos(hwnd, None, *rect, 0x0014):
            raise OSError("O Windows recusou o posicionamento. Aplicativos elevados ou protegidos podem impedir esta operação")

    def show(self, hwnd, state):
        self.user.ShowWindow(hwnd, state)

    def focus(self, hwnd):
        return bool(self.user.SetForegroundWindow(hwnd))

    def maximized(self, hwnd):
        return bool(self.user.IsZoomed(hwnd))
