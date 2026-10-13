"""Учасник двофазної фіксації — банк із одним рахунком.

    python uchasnyk.py --imya U1
    python uchasnyk.py --imya U2
    python uchasnyk.py --imya U3
    python uchasnyk.py --imya U2 --holos ni           # завжди голосує «ні»
    python uchasnyk.py --imya U3 --samovilno-cherez 5  # ⭐2: сам скасує, прочекавши 5 с
    python uchasnyk.py --imya U1 --bez-zhurnalu        # ⭐3: нічого не пише на диск

На рахунку спершу 1000 грн. Кожен крок протоколу учасник записує в zhurnal-<ім'я>.txt
(журнал попереднього запису): після перезапуску він пам'ятає, що вже пообіцяв.

Поки учасник «готовий» (проголосував «так» і чекає рішення), рахунок ЗАБЛОКОВАНО:
жодна інша операція — зняти готівку, інший переказ — не пройде.
Зупинити — Ctrl+C.
"""

import argparse
import json
import os
import socket
import sys
import threading
import time

HOST = "127.0.0.1"
UCHASNYKY = {"U1": 50061, "U2": 50062, "U3": 50063}
POCHATKOVYI = 1000


def zapyt(port, povidomlennia, taimaut=3.0):
    s = socket.create_connection((HOST, port), timeout=taimaut)
    try:
        f = s.makefile("rwb")
        f.write((json.dumps(povidomlennia, ensure_ascii=False) + "\n").encode())
        f.flush()
        ryadok = f.readline()
        if not ryadok:
            raise ConnectionError("відповіді немає")
        return json.loads(ryadok.decode())
    finally:
        s.close()


class Uchasnyk:
    def __init__(self, args):
        self.imya = args.imya
        self.port = UCHASNYKY[args.imya]
        self.args = args
        self.zhurnal = None if args.bez_zhurnalu else f"zhurnal-{self.imya}.txt"
        self.zamok = threading.Lock()
        self.zalyshok = POCHATKOVYI
        self.gotovyi = None                  # {"tx", "delta", "z"} — пообіцяли й чекаємо
        self.rishennia = {}                  # tx → "zafiksovano" / "skasovano"
        self.vidnovyty()

    def druk(self, tekst):
        print(f"[{self.imya} {time.strftime('%H:%M:%S')}] {tekst}", flush=True)

    def pysaty(self, zapys):
        if self.zhurnal:
            with open(self.zhurnal, "a", encoding="utf-8") as f:
                f.write(json.dumps(zapys, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def vidnovyty(self):
        """Після перезапуску — відтворити стан із журналу."""
        if not self.zhurnal or not os.path.exists(self.zhurnal):
            return
        with open(self.zhurnal, encoding="utf-8") as f:
            for r in f:
                z = json.loads(r)
                if z["podiya"] == "gotovyi":
                    self.gotovyi = {"tx": z["tx"], "delta": z["delta"], "z": z["chas"]}
                elif z["podiya"] in ("zafiksovano", "skasovano"):
                    self.rishennia[z["tx"]] = z["podiya"]
                    if z["podiya"] == "zafiksovano":
                        self.zalyshok += z["delta"]
                    if self.gotovyi and self.gotovyi["tx"] == z["tx"]:
                        self.gotovyi = None
                elif z["podiya"] == "operatsiia":
                    self.zalyshok += z["delta"]
        stan = (f"⚠ ГОТОВИЙ по {self.gotovyi['tx']} — рішення не знаю, рахунок заблоковано"
                if self.gotovyi else "вільний")
        self.druk(f"відновлено з журналу: залишок {self.zalyshok} грн · {stan}")

    def zavershyty(self, tx, rishennia, chomu=""):
        with self.zamok:
            if not self.gotovyi or self.gotovyi["tx"] != tx:
                self.rishennia.setdefault(tx, rishennia)
                return
            delta = self.gotovyi["delta"]
            if rishennia == "zafiksovano":
                self.zalyshok += delta
            chekav = time.time() - self.gotovyi["z"]
            self.gotovyi = None
            self.rishennia[tx] = rishennia
            self.pysaty({"tx": tx, "podiya": rishennia, "delta": delta, "chas": time.time()})
        znak = "✔ ЗАФІКСОВАНО" if rishennia == "zafiksovano" else "✖ СКАСОВАНО"
        self.druk(f"{znak} {tx} ({delta:+d} грн) · залишок {self.zalyshok} грн · "
                  f"рахунок був заблокований {chekav:.1f} с{chomu}")

    def storozh(self):
        """⭐2: скасувати самовільно, якщо рішення не приходить."""
        while True:
            time.sleep(0.2)
            g = self.gotovyi
            if g and time.time() - g["z"] > self.args.samovilno_cherez:
                self.druk(f"⚠ рішення по {g['tx']} немає {self.args.samovilno_cherez:g} с — "
                          f"СКАСОВУЮ САМ (хоча обіцяв «так»)")
                self.zavershyty(g["tx"], "skasovano", " · самовільно")

    def obrobyty(self, z):
        dia = z.get("dia")
        if dia == "pidhotuvatysia":
            with self.zamok:
                if self.gotovyi:
                    self.druk(f"голосую НІ по {z['tx']}: рахунок заблоковано транзакцією {self.gotovyi['tx']}")
                    return {"holos": "ni", "chomu": "заблоковано іншою транзакцією"}
                if self.args.holos == "ni" or self.zalyshok + z["delta"] < 0:
                    self.rishennia[z["tx"]] = "skasovano"
                    self.druk(f"голосую НІ по {z['tx']} ({z['delta']:+d} грн)")
                    return {"holos": "ni"}
                self.gotovyi = {"tx": z["tx"], "delta": z["delta"], "z": time.time()}
                self.pysaty({"tx": z["tx"], "podiya": "gotovyi", "delta": z["delta"], "chas": time.time()})
            self.druk(f"голосую ТАК по {z['tx']} ({z['delta']:+d} грн) — пообіцяв, рахунок заблоковано, чекаю рішення")
            return {"holos": "tak"}
        if dia in ("zafiksuvaty", "skasuvaty"):
            self.zavershyty(z["tx"], "zafiksovano" if dia == "zafiksuvaty" else "skasovano")
            return {"ok": True}
        if dia == "operatsiia":
            with self.zamok:
                if self.gotovyi:
                    chekaie = time.time() - self.gotovyi["z"]
                    return {"ok": False, "chomu": f"рахунок заблоковано транзакцією {self.gotovyi['tx']} "
                                                  f"уже {chekaie:.1f} с"}
                if self.zalyshok + z["delta"] < 0:
                    return {"ok": False, "chomu": "недостатньо коштів"}
                self.zalyshok += z["delta"]
                self.pysaty({"tx": "-", "podiya": "operatsiia", "delta": z["delta"], "chas": time.time()})
                return {"ok": True, "zalyshok": self.zalyshok}
        if dia == "stan":
            g = self.gotovyi
            return {"imya": self.imya, "zalyshok": self.zalyshok,
                    "gotovyi": ({"tx": g["tx"], "delta": g["delta"], "sekund": round(time.time() - g["z"], 1)}
                                if g else None),
                    "rishennia": self.rishennia}
        return {"ok": False, "chomu": f"невідома дія {dia!r}"}

    def zyednannia(self, conn):
        try:
            f = conn.makefile("rwb")
            r = f.readline()
            if r:
                f.write((json.dumps(self.obrobyty(json.loads(r.decode())), ensure_ascii=False) + "\n").encode())
                f.flush()
        except (OSError, ValueError):
            pass
        finally:
            conn.close()


def main():
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser()
    p.add_argument("--imya", choices=sorted(UCHASNYKY), required=True)
    p.add_argument("--holos", choices=["tak", "ni"], default="tak", help="як голосувати")
    p.add_argument("--samovilno-cherez", type=float, default=0,
                   help="⭐2: скасувати самому, якщо рішення немає стільки секунд")
    p.add_argument("--bez-zhurnalu", action="store_true", help="⭐3: не писати журнал на диск")
    args = p.parse_args()

    u = Uchasnyk(args)
    if args.samovilno_cherez:
        threading.Thread(target=u.storozh, daemon=True).start()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, u.port))
    s.listen(16)
    s.settimeout(0.5)
    u.druk(f"слухаю :{u.port} · залишок {u.zalyshok} грн"
           + (" · голосую завжди НІ" if args.holos == "ni" else "")
           + (" · БЕЗ журналу" if args.bez_zhurnalu else ""))
    try:
        while True:
            try:
                conn, _ = s.accept()
            except socket.timeout:
                continue
            threading.Thread(target=u.zyednannia, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        u.druk("зупинено")
    finally:
        s.close()


if __name__ == "__main__":
    main()
