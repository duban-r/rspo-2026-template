"""Служба «журнал замірів» — приймає заміри по мережі й веде лічильник.

Каркас той самий, що в прикладі 04-19 підручника Tanenbaum & van Steen
(сокет, `recv`, `send`), тільки повідомлення — рядки JSON, по одному на рядок.

Запуск:
    python sluzhba.py                 # слухає 127.0.0.1:50007
    python sluzhba.py --port 50008

Служба навмисно написана **чесно**: вона не втрачає й не дублює нічого сама.
Усе, що зламається на практичній, зламається в мережі між клієнтом і нею.
"""

import argparse
import json
import socket
import threading
import time

HOST = "127.0.0.1"
PORT = 50007


class Zhurnal:
    """Те, що службі треба зберігати. Захищено замком — тема тижня 5."""

    def __init__(self):
        self.zamiry = []
        self.bacheni_kliuchi = {}          # ключ ідемпотентності -> відповідь
        self.zamok = threading.Lock()

    def dodaty(self, zapys, kliuch=None):
        with self.zamok:
            if kliuch is not None and kliuch in self.bacheni_kliuchi:
                # цей самий запис уже приймали — повертаємо ту саму відповідь
                vidpovid = dict(self.bacheni_kliuchi[kliuch])
                vidpovid["povtor"] = True
                return vidpovid
            self.zamiry.append(zapys)
            vidpovid = {"status": "ok", "vsogo": len(self.zamiry), "povtor": False}
            if kliuch is not None:
                self.bacheni_kliuchi[kliuch] = {"status": "ok", "vsogo": len(self.zamiry)}
            return vidpovid

    def stan(self):
        with self.zamok:
            return {"status": "ok", "vsogo": len(self.zamiry),
                    "unikalnyh_kliuchiv": len(self.bacheni_kliuchi)}


def obrobyty_kliyenta(conn, addr, zhurnal, robota_ms):
    conn_file = conn.makefile("rwb")
    try:
        for ryadok in conn_file:
            ryadok = ryadok.strip()
            if not ryadok:
                break
            try:
                zapyt = json.loads(ryadok)
            except json.JSONDecodeError:
                vidpovid = {"status": "pomylka", "chomu": "не JSON"}
            else:
                if zapyt.get("dia") == "stan":
                    vidpovid = zhurnal.stan()
                else:
                    if robota_ms:
                        time.sleep(robota_ms / 1000)      # імітація корисної роботи
                    vidpovid = zhurnal.dodaty(zapyt.get("zapys"), zapyt.get("kliuch"))
            conn_file.write((json.dumps(vidpovid, ensure_ascii=False) + "\n").encode())
            conn_file.flush()
    except (ConnectionResetError, ConnectionAbortedError):
        print(f"[служба] клієнт {addr} обірвав з'єднання")
    finally:
        conn_file.close()
        conn.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--robota-ms", type=int, default=0,
                   help="скільки мілісекунд служба «працює» над кожним записом")
    args = p.parse_args()

    zhurnal = Zhurnal()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, args.port))
    s.listen(8)
    print(f"[служба] слухаю {HOST}:{args.port} — Ctrl+C щоб зупинити")
    try:
        while True:
            conn, addr = s.accept()
            threading.Thread(target=obrobyty_kliyenta,
                             args=(conn, addr, zhurnal, args.robota_ms),
                             daemon=True).start()
    except KeyboardInterrupt:
        print(f"\n[служба] зупинено. Прийнято записів: {zhurnal.stan()['vsogo']}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
