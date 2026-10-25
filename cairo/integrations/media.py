"""Bounded system media commands, without arbitrary key or mouse injection."""

import ctypes
import sys
from ctypes import wintypes

KEYS = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "stop": 0xB2,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "mute": 0xAD,
}
LABELS = {
    "play_pause": "alternar reprodução/pausa",
    "next": "próxima faixa",
    "previous": "faixa anterior",
    "stop": "parar reprodução",
    "volume_up": "aumentar volume",
    "volume_down": "diminuir volume",
    "mute": "alternar mudo",
}


def media_action(action: str) -> dict:
    if action not in KEYS:
        raise ValueError("Comando de mídia inválido")
    if sys.platform != "win32":
        raise OSError("Controles de mídia requerem Windows")

    class Keyboard(ctypes.Structure):
        _fields_ = [
            ("vk", wintypes.WORD),
            ("scan", wintypes.WORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("extra", ctypes.c_size_t),
        ]

    class Mouse(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("data", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("extra", ctypes.c_size_t),
        ]

    class Payload(ctypes.Union):
        _fields_ = [("keyboard", Keyboard), ("mouse", Mouse)]

    class Input(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("payload", Payload)]

    events = (Input * 2)()
    for i, flags in enumerate((0, 2)):
        events[i].type = 1
        events[i].payload.keyboard = Keyboard(KEYS[action], 0, flags, 0, 0)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    count = user32.SendInput(2, events, ctypes.sizeof(Input))
    if count != 2:
        # Best effort key-up if Windows accepted only the down event.
        if count == 1:
            user32.SendInput(1, ctypes.byref(events[1]), ctypes.sizeof(Input))
        raise OSError("Windows não aceitou o comando de mídia completo")
    return {
        "requested": True,
        "action": action,
        "message": "Enviei ao Windows: "
        + LABELS[action]
        + ". O aplicativo de mídia ativo precisa aceitar esse controle.",
    }
