"""Native controls used only by opt-in desktop automation tests."""

import ctypes
import sys
from ctypes import wintypes

user = ctypes.WinDLL("user32", use_last_error=True)
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
callback = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WindowClass(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("proc", callback),
        ("cls_extra", ctypes.c_int),
        ("wnd_extra", ctypes.c_int),
        ("instance", wintypes.HINSTANCE),
        ("icon", wintypes.HICON),
        ("cursor", wintypes.HANDLE),
        ("background", wintypes.HBRUSH),
        ("menu", wintypes.LPCWSTR),
        ("name", wintypes.LPCWSTR),
    ]


kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel.GetModuleHandleW.restype = wintypes.HMODULE
user.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user.DefWindowProcW.restype = ctypes.c_ssize_t
user.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    ctypes.c_void_p,
]
user.CreateWindowExW.restype = wintypes.HWND
user.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user.RegisterClassW.argtypes = [ctypes.POINTER(WindowClass)]
user.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user.DispatchMessageW.restype = ctypes.c_ssize_t
handles = {}


@callback
def procedure(hwnd, message, wparam, lparam):
    if message == 0x0111 and (wparam & 0xFFFF) == 100:
        text = ctypes.create_unicode_buffer(4096)
        user.GetWindowTextW(handles["edit"], text, 4096)
        user.SetWindowTextW(handles["status"], "CAIRO APP OK " + text.value)
        return 0
    if message == 0x0002:
        user.PostQuitMessage(0)
        return 0
    return user.DefWindowProcW(hwnd, message, wparam, lparam)


instance = kernel.GetModuleHandleW(None)
spec = WindowClass(
    0,
    procedure,
    0,
    0,
    instance,
    None,
    None,
    wintypes.HBRUSH(6),
    None,
    "CairoControlFixture",
)
if not user.RegisterClassW(ctypes.byref(spec)):
    raise OSError("Fixture class registration failed")
main = user.CreateWindowExW(
    0,
    spec.name,
    sys.argv[1],
    0x10CF0000,
    120,
    120,
    600,
    230,
    None,
    None,
    instance,
    None,
)
if not main:
    raise OSError("Fixture window creation failed")
handles["edit"] = user.CreateWindowExW(
    0, "EDIT", "", 0x50810080, 20, 20, 530, 30, main, None, instance, None
)
handles["button"] = user.CreateWindowExW(
    0,
    "BUTTON",
    "Aplicar",
    0x50010000,
    20,
    65,
    130,
    35,
    main,
    wintypes.HMENU(100),
    instance,
    None,
)
handles["status"] = user.CreateWindowExW(
    0, "STATIC", "Aguardando", 0x50000000, 20, 115, 530, 35, main, None, instance, None
)
message = wintypes.MSG()
while user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
    user.TranslateMessage(ctypes.byref(message))
    user.DispatchMessageW(ctypes.byref(message))
