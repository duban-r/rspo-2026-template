"""Служба «журнал замірів» — версія теми 9: уміє бути зі станом і без стану.

    python sluzhba.py --port 50007 --imya A
    python sluzhba.py --port 50008 --imya B
    python sluzhba.py --port 50007 --imya A --shovyshche 50020

Перші два запуски — дві **незалежні** копії: у кожної свій журнал у пам'яті.
Третій — копія **без стану**: журнал вона не тримає, а передає у спільне
сховище (`shovyshche.py`), тож усі копії бачать одне й те саме.

У кожній відповіді є поле `vuzol` — яка саме копія відповіла.
"""

import argparse
import hashlib
import json
import socket
import threading
import time

HOST = "127.0.0.1"


class Zhurnal:
    def __init__(self):
        self.zamiry = []
        self.kliuchi = {}
        self.zamok = threading.Lock()

    def dodaty(self, zapys, kliuch=None):
        with self.zamok:
            if kliuch is not None and kliuch in self.kliuchi:
                return {"status": "ok", "vsogo": self.kliuchi[kliuch], "povtor": True}
            self.zamiry.append(zapys)
            if kliuch is not None:
                self.kliuchi[kliuch] = len(self.zamiry)
            return {"status": "ok", "vsogo": len(self.zamiry), "povtor": False}

    def stan(self):
        with self.zamok:
            return {"status": "ok", "vsogo": len(self.zamiry),
                    "unikalnyh_kliuchiv": len(self.kliuchi)}


def spytaty_shovyshche(port, zapyt, taimaut=3):
    s = socket.create_connection((HOST, port), timeout=taimaut)
    try:
        f = s.makefile("rwb")
        f.write((json.dumps(zapyt, ensure_ascii=False) + "\n").encode())
        f.flush()
        ryadok = f.readline()
        if not ryadok:
            raise ConnectionError("сховище закрило з'єднання")
        return json.loads(ryadok.decode())
    finally:
        s.close()


def porakhuvaty(rundiv):
    """Процесорна робота над запитом: саме вона робить копію вузьким місцем."""
    h = b"zamir"
    for _ in range(rundiv):
        h = hashlib.sha256(h).digest()
    return h


def obrobyty(conn, zhurnal, imya, shovyshche, robota_ms, robota_cpu):
    try:
        f = conn.makefile("rwb")
        for ryadok in f:
            ryadok = ryadok.strip()
            if not ryadok:
                break
            zapyt = json.loads(ryadok)
            if robota_ms:
                time.sleep(robota_ms / 1000)
            if robota_cpu:
                porakhuvaty(robota_cpu)
            if shovyshche:
                try:
                    vidpovid = spytaty_shovyshche(shovyshche, zapyt)
                except OSError as e:
                    vidpovid = {"status": "pomylka", "chomu": f"сховище недоступне: {e}"}
            elif zapyt.get("dia") == "stan":
                vidpovid = zhurnal.stan()
            else:
                vidpovid = zhurnal.dodaty(zapyt.get("zapys"), zapyt.get("kliuch"))
            vidpovid["vuzol"] = imya
            f.write((json.dumps(vidpovid, ensure_ascii=False) + "\n").encode())
            f.flush()
    except (OSError, ValueError):
        pass
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=50007)
    p.add_argument("--imya", default="A", help="ім'я вузла — видно в кожній відповіді")
    p.add_argument("--shovyshche", type=int, default=None,
                   help="порт спільного сховища; з ним копія стає БЕЗ СТАНУ")
    p.add_argument("--robota-ms", type=int, default=0,
                   help="скільки мілісекунд копія ЧЕКАЄ над запитом (імітація диска)")
    p.add_argument("--robota-cpu", type=int, default=0,
                   help="скільки раундів хешування копія РАХУЄ над запитом")
    args = p.parse_args()

    zhurnal = Zhurnal()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, args.port))
    s.listen(64)
    rezhym = f"без стану → сховище :{args.shovyshche}" if args.shovyshche else "стан у власній пам'яті"
    print(f"[{args.imya}] слухаю {HOST}:{args.port} · {rezhym}")
    try:
        while True:
            conn, _ = s.accept()
            threading.Thread(target=obrobyty,
                             args=(conn, zhurnal, args.imya, args.shovyshche,
                                   args.robota_ms, args.robota_cpu),
                             daemon=True).start()
    except KeyboardInterrupt:
        print(f"\n[{args.imya}] зупинено. У власному журналі: {zhurnal.stan()['vsogo']}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
