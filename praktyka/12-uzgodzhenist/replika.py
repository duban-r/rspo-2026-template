"""Репліка сховища «ключ → значення»: асинхронна реплікація, розрив мережі, кворум.

    python replika.py --imya R1
    python replika.py --imya R2
    python replika.py --imya R3

Три репліки знають одна одну (порти 50051–50053). Запис, що прийшов на репліку,
застосовується одразу, а сусідам летить **потім** — через --zatrymka-ms (типово 300 мс,
як повільний канал між дата-центрами). Отримавши чужу версію, репліка зливає її зі своєю
функцією `obyednaty` з `zlyttia.py`.

Годинник R3 навмисно поспішає на 0,5 с (--zsuv): від нього залежить, чий запис «новіший».

Команди надсилає `kliyent_kv.py`; протокол — один рядок JSON на запит і на відповідь.
Зупинити — Ctrl+C.
"""

import argparse
import json
import socket
import sys
import threading
import time
import uuid

import zlyttia

HOST = "127.0.0.1"
REPLIKY = {"R1": (50051, 0.0), "R2": (50052, 0.0), "R3": (50053, 0.5)}   # порт, зсув годинника


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


class Replika:
    def __init__(self, args):
        self.imya = args.imya
        self.port, zsuv = REPLIKY[args.imya]
        self.zsuv = zsuv if args.zsuv is None else args.zsuv
        self.zatrymka = args.zatrymka_ms / 1000
        self.susidy = {i: v[0] for i, v in REPLIKY.items() if i != self.imya}
        self.dani = {}                       # ключ → {"znach", "ts", "vuzol"}
        self.rozirvano = set()               # з ким зараз немає зв'язку
        self.zamok = threading.Lock()
        self.lich = {"записів": 0, "реплікацій прийнято": 0, "реплікацій загублено в розриві": 0}

    def chas(self):
        return time.time() + self.zsuv

    def druk(self, tekst):
        print(f"[{self.imya}] {tekst}", flush=True)

    # ------------------------------------------------------------ дані
    def zastosuvaty_lokalno(self, kliuch, dia, znach):
        """Запис клієнта на цю репліку. Повертає нову версію."""
        with self.zamok:
            stara = self.dani.get(kliuch)
            if dia == "dodaty":
                spysok = list(stara["znach"]) if stara and isinstance(stara["znach"], list) else []
                spysok.append({"id": uuid.uuid4().hex[:6], "tekst": znach, "vuzol": self.imya})
                znach = spysok
            versiya = {"znach": znach, "ts": round(self.chas(), 4), "vuzol": self.imya}
            self.dani[kliuch] = versiya
            self.lich["записів"] += 1
            return versiya

    def zlyty(self, kliuch, chuzha):
        with self.zamok:
            mia = self.dani.get(kliuch)
            rez = zlyttia.obyednaty(mia, chuzha)
            self.dani[kliuch] = rez
            self.lich["реплікацій прийнято"] += 1
            return mia != rez

    # ------------------------------------------------------------ реплікація
    def nadislaty_susidu(self, imya, kliuch, versiya, zatrymka):
        time.sleep(zatrymka)
        if imya in self.rozirvano:
            self.lich["реплікацій загублено в розриві"] += 1
            return False
        try:
            v = zapyt(self.susidy[imya], {"dia": "replika", "vid": self.imya,
                                          "kliuch": kliuch, "versiya": versiya}, taimaut=2)
            return bool(v.get("ok"))
        except OSError:
            return False

    def replikuvaty_asynkhronno(self, kliuch, versiya):
        for imya in self.susidy:
            threading.Thread(target=self.nadislaty_susidu,
                             args=(imya, kliuch, versiya, self.zatrymka), daemon=True).start()

    def replikuvaty_z_kvorumom(self, kliuch, versiya, W):
        """Чекати, доки W−1 сусідів підтвердять; решті — асинхронно."""
        potribno = W - 1
        if potribno <= 0:
            self.replikuvaty_asynkhronno(kliuch, versiya)
            return True, 0
        pidtverdyly, gotovo = [0], threading.Event()
        zamok = threading.Lock()

        def odyn(imya):
            if self.nadislaty_susidu(imya, kliuch, versiya, self.zatrymka):
                with zamok:
                    pidtverdyly[0] += 1
                    if pidtverdyly[0] >= potribno:
                        gotovo.set()

        for imya in self.susidy:
            threading.Thread(target=odyn, args=(imya,), daemon=True).start()
        gotovo.wait(timeout=self.zatrymka + 2.5)
        return pidtverdyly[0] >= potribno, pidtverdyly[0]

    def antyentropiia(self):
        """Після відновлення зв'язку — розіслати все, що маємо (з тією ж затримкою)."""
        with self.zamok:
            kopiia = dict(self.dani)
        for kliuch, versiya in kopiia.items():
            self.replikuvaty_asynkhronno(kliuch, versiya)

    # ------------------------------------------------------------ запити
    def obrobyty(self, z):
        dia = z.get("dia")
        if dia in ("zapysaty", "dodaty"):
            W = int(z.get("W", 1))
            dostupnyh = 1 + sum(1 for i in self.susidy if i not in self.rozirvano)
            if W > dostupnyh:
                return {"ok": False, "chomu": f"відмовлено: доступних копій {dostupnyh}, потрібно W={W}"}
            versiya = self.zastosuvaty_lokalno(z["kliuch"], dia, z["znach"])
            ok, pidtv = self.replikuvaty_z_kvorumom(z["kliuch"], versiya, W)
            if not ok:
                return {"ok": False, "chomu": f"кворуму немає: підтвердили {pidtv} з {W - 1} — "
                                              f"але запис уже лежить на {self.imya}"}
            return {"ok": True, "versiya": versiya}
        if dia == "chytaty":
            R = int(z.get("R", 1))
            with self.zamok:
                mia = self.dani.get(z["kliuch"])
            if R <= 1:
                return {"ok": True, "versiya": mia, "vid": [self.imya]}
            dostupni = [i for i in self.susidy if i not in self.rozirvano]
            if R > 1 + len(dostupni):
                return {"ok": False, "chomu": f"відмовлено: доступних копій {1 + len(dostupni)}, потрібно R={R}"}
            rez, vid = mia, [self.imya]
            for imya in dostupni:
                if len(vid) >= R:
                    break
                try:
                    v = zapyt(self.susidy[imya], {"dia": "chytaty", "kliuch": z["kliuch"]}, taimaut=2)
                    rez = zlyttia.obyednaty(rez, v.get("versiya"))
                    vid.append(imya)
                except OSError:
                    pass
            if len(vid) < R:
                return {"ok": False, "chomu": f"кворуму читання немає: відповіли {len(vid)} з {R}"}
            return {"ok": True, "versiya": rez, "vid": vid}
        if dia == "replika":
            if z["vid"] in self.rozirvano:
                return {"ok": False, "chomu": "розрив"}
            zminylos = self.zlyty(z["kliuch"], z["versiya"])
            return {"ok": True, "zminylos": zminylos}
        if dia == "rozryv":
            self.rozirvano = set(z["z"]) - {self.imya}
            self.druk(f"✂ розрив: немає зв'язку з {', '.join(sorted(self.rozirvano)) or 'ніким'}")
            return {"ok": True}
        if dia == "zyednaty":
            self.rozirvano = set()
            self.druk("🔗 зв'язок відновлено — розсилаю все, що маю")
            self.antyentropiia()
            return {"ok": True}
        if dia == "stan":
            with self.zamok:
                return {"ok": True, "imya": self.imya, "dani": self.dani,
                        "rozirvano": sorted(self.rozirvano), "lich": dict(self.lich)}
        return {"ok": False, "chomu": f"невідома дія {dia!r}"}

    def zyednannia(self, conn):
        try:
            f = conn.makefile("rwb")
            ryadok = f.readline()
            if ryadok:
                vidpovid = self.obrobyty(json.loads(ryadok.decode()))
                f.write((json.dumps(vidpovid, ensure_ascii=False) + "\n").encode())
                f.flush()
        except (OSError, ValueError) as e:
            self.druk(f"помилка запиту: {type(e).__name__}: {e}")
        finally:
            conn.close()


def main():
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser()
    p.add_argument("--imya", choices=sorted(REPLIKY), required=True)
    p.add_argument("--zatrymka-ms", type=float, default=300,
                   help="скільки летить реплікація до сусіда, мс")
    p.add_argument("--zsuv", type=float, default=None, help="зсув годинника цієї репліки, с")
    args = p.parse_args()

    r = Replika(args)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, r.port))
    s.listen(64)
    s.settimeout(0.5)
    r.druk(f"слухаю {HOST}:{r.port} · реплікація +{args.zatrymka_ms:g} мс · годинник {r.zsuv:+.1f} с · "
           f"злиття: {zlyttia.obyednaty.__doc__.strip().splitlines()[0]}")
    try:
        while True:
            try:
                conn, _ = s.accept()
            except socket.timeout:
                continue
            threading.Thread(target=r.zyednannia, args=(conn,), daemon=True).start()
    except KeyboardInterrupt:
        r.druk(f"зупинено · {r.lich}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
