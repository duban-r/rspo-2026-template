"""Балансувальник — одна адреса для клієнта, кілька копій служби за нею.

    python balansuvalnyk.py --vuzly 50007 50008
    python balansuvalnyk.py --vuzly 50007 50008 --bez-perevirky

Роздає з'єднання по черзі (round-robin) і раз на секунду перевіряє, чи живі
вузли. Мертвий вузол виключається з черги, живий — повертається сам.

З `--bez-perevirky` перевірки немає: побачите, що буває, коли балансувальник
вірить у списку адрес більше, ніж власним очам.

Раз на 5 секунд друкує, скільки з'єднань дісталось кожному вузлу.
"""

import argparse
import json
import socket
import threading
import time
import itertools

HOST = "127.0.0.1"


class Vuzol:
    def __init__(self, port):
        self.port = port
        self.zhyvyi = True
        self.zednan = 0
        self.vidmov = 0

    def __repr__(self):
        stan = "живий" if self.zhyvyi else "МЕРТВИЙ"
        return f":{self.port} {stan} з'єднань {self.zednan} відмов {self.vidmov}"


def perevirka(vuzly, stop, period=1.0):
    """Раз на секунду питаємо в кожного вузла «стан»."""
    while not stop.wait(period):
        for v in vuzly:
            try:
                s = socket.create_connection((HOST, v.port), timeout=0.5)
                f = s.makefile("rwb")
                f.write(b'{"dia": "stan"}\n')
                f.flush()
                ok = bool(f.readline())
                s.close()
            except OSError:
                ok = False
            if ok != v.zhyvyi:
                print(f"[балансувальник] вузол :{v.port} —"
                      f" {'ожив' if ok else 'НЕ ВІДПОВІДАЄ, виключаю'}")
            v.zhyvyi = ok


def perekachaty(a, b):
    try:
        while True:
            d = a.recv(4096)
            if not d:
                break
            b.sendall(d)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def obsluzhyty(kliyent, vuzly, cherga, perevirka_uvimknena):
    kandydaty = [v for v in vuzly if v.zhyvyi] if perevirka_uvimknena else list(vuzly)
    if not kandydaty:
        print("[балансувальник] живих вузлів немає — відмовляю клієнту")
        kliyent.close()
        return
    v = kandydaty[next(cherga) % len(kandydaty)]
    try:
        sluzhba = socket.create_connection((HOST, v.port), timeout=2)
    except OSError:
        v.vidmov += 1
        print(f"[балансувальник] вузол :{v.port} не приймає з'єднання")
        kliyent.close()
        return
    v.zednan += 1
    t1 = threading.Thread(target=perekachaty, args=(kliyent, sluzhba), daemon=True)
    t2 = threading.Thread(target=perekachaty, args=(sluzhba, kliyent), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=50000, help="порт для клієнтів")
    p.add_argument("--vuzly", type=int, nargs="+", default=[50007, 50008])
    p.add_argument("--bez-perevirky", action="store_true",
                   help="не перевіряти, чи живі вузли")
    args = p.parse_args()

    vuzly = [Vuzol(port) for port in args.vuzly]
    cherga = itertools.count()
    stop = threading.Event()
    if not args.bez_perevirky:
        threading.Thread(target=perevirka, args=(vuzly, stop), daemon=True).start()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, args.port))
    s.listen(64)
    print(f"[балансувальник] клієнти → :{args.port} → вузли "
          f"{', '.join(':' + str(v.port) for v in vuzly)}"
          f"{' · без перевірки живості' if args.bez_perevirky else ''}")

    def zvit():
        while not stop.wait(5.0):
            print("[балансувальник] " + " | ".join(repr(v) for v in vuzly))

    threading.Thread(target=zvit, daemon=True).start()

    try:
        while True:
            kliyent, _ = s.accept()
            threading.Thread(target=obsluzhyty,
                             args=(kliyent, vuzly, cherga, not args.bez_perevirky),
                             daemon=True).start()
    except KeyboardInterrupt:
        stop.set()
        print("\n[балансувальник] підсумок: " + " | ".join(repr(v) for v in vuzly))
    finally:
        s.close()


if __name__ == "__main__":
    main()
