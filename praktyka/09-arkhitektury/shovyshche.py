"""Спільне сховище — єдиний журнал для всіх копій служби.

    python shovyshche.py --port 50020

Протокол той самий, що в служби. Різниця одна: сховище **одне на всіх**,
і саме тому копії служби можуть бути без стану й взаємозамінними.

⚠️ Зверніть увагу, що ми щойно зробили: прибрали вузьке місце зі служби
й створили нове — тут. Це не помилка, це компроміс, і на парі ви його
назвете вголос.
"""

import argparse
import json
import socket
import threading


HOST = "127.0.0.1"


class Shovyshche:
    def __init__(self):
        self.zapysy = []
        self.kliuchi = {}
        self.zvernen = 0
        self.zamok = threading.Lock()

    def obrobyty(self, zapyt):
        with self.zamok:
            self.zvernen += 1
            if zapyt.get("dia") == "stan":
                return {"status": "ok", "vsogo": len(self.zapysy),
                        "unikalnyh_kliuchiv": len(self.kliuchi),
                        "zvernen_do_shovyshcha": self.zvernen}
            kliuch = zapyt.get("kliuch")
            if kliuch is not None and kliuch in self.kliuchi:
                return {"status": "ok", "vsogo": self.kliuchi[kliuch], "povtor": True}
            self.zapysy.append(zapyt.get("zapys"))
            if kliuch is not None:
                self.kliuchi[kliuch] = len(self.zapysy)
            return {"status": "ok", "vsogo": len(self.zapysy), "povtor": False}


def obsluzhyty(conn, shov):
    try:
        f = conn.makefile("rwb")
        for ryadok in f:
            if not ryadok.strip():
                break
            vidpovid = shov.obrobyty(json.loads(ryadok))
            f.write((json.dumps(vidpovid, ensure_ascii=False) + "\n").encode())
            f.flush()
    except (OSError, ValueError):
        pass
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=50020)
    args = p.parse_args()

    shov = Shovyshche()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, args.port))
    s.listen(64)
    print(f"[сховище] слухаю {HOST}:{args.port} — один журнал на всі копії служби")
    try:
        while True:
            conn, _ = s.accept()
            threading.Thread(target=obsluzhyty, args=(conn, shov), daemon=True).start()
    except KeyboardInterrupt:
        print(f"\n[сховище] зупинено. Записів: {len(shov.zapysy)}"
              f" · звернень: {shov.zvernen}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
