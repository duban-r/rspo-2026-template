"""Рамка повідомлення: як відділити одне повідомлення від наступного в потоці TCP.

Формат: 4 байти довжини (big-endian) + JSON у UTF-8.

    nadislaty(sock, {"dia": "stan"})
    vidpovid = otrymaty(sock)

`nadislaty` написано правильно. `otrymaty` — **наївно**, як пишуть у першому
прикладі з інтернету, і саме її ви виправляєте на кроці 1.
Перевірка: `python perevirka_ramky.py`.

Цей файл імпортують `koordynator.py`, `pratsivnyk.py` і `sposterigach.py`.
Брокер має власну рамку й від цього файлу не залежить.
"""

import json
import os
import socket
import struct

HOST = os.environ.get("BROKER_HOST", "127.0.0.1")   # у контейнерах — ім'я служби брокера


def nadislaty(sock, obj):
    """Повідомлення = довжина (4 байти) + сам JSON. sendall, а не send: send може
    відправити лише частину й повернути, скільки встиг."""
    dani = json.dumps(obj, ensure_ascii=False).encode()
    sock.sendall(struct.pack(">I", len(dani)) + dani)


def otrymaty(sock):
    """⚠️ НАІВНА ВЕРСІЯ — виправити на кроці 1.

    Має повернути рівно ОДНЕ повідомлення (dict), яке надіслала `nadislaty`.
    Якщо з'єднання закрилось посеред повідомлення — підняти ConnectionError.
    """
    dani = sock.recv(65536)
    if not dani:
        raise ConnectionError("з'єднання закрито")
    return json.loads(dani[4:].decode())


# --------------------------------------------------------- зручні обгортки

def pidkliuchytys(port, taimaut=None):
    sock = socket.create_connection((HOST, port), timeout=taimaut)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return sock


def zapyt(sock, obj):
    """Надіслати запит і дочекатись відповіді — синхронно, як RPC."""
    nadislaty(sock, obj)
    return otrymaty(sock)
