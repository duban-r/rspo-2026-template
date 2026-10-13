"""Брокер повідомлень — черги й публікація-підписка. Стандартна бібліотека, без Redis.

    python broker.py
    python broker.py --pidtverdzhennya          # повідомлення зникає лише після «зроблено»
    python broker.py --merezha-ms 5             # кожна відповідь «летить» 5 мс, як у справжній мережі

Що вміє (кожне повідомлення — 4 байти довжини + JSON):

  {"dia": "poklasty", "cherga": "zavdannya", "dani": {...}}   покласти в чергу
  {"dia": "vzyaty", "cherga": "zavdannya", "chekaty": 1}      забрати ОДНЕ (чекати до 1 с)
  {"dia": "pidtverdyty", "id": 17}                            «зроблено» (лише з --pidtverdzhennya)
  {"dia": "pidpysatys", "tema": "postup"}                     далі це з'єднання лише слухає тему
  {"dia": "opublikuvaty", "tema": "postup", "dani": {...}}    розіслати ВСІМ підписникам
  {"dia": "ochystyty", "cherga": "zavdannya"}                 викинути все, що лежить у черзі
  {"dia": "stan"}                                             довжини черг, підписники, лічильники

Черга: кожне повідомлення отримає **один** зі споживачів, і воно лежить, доки
його не заберуть. Тема: повідомлення отримають **усі**, хто підписаний саме зараз;
хто не слухав — не отримає ніколи.

Брокер має власну правильну обробку меж повідомлень і не залежить від `ramka.py`.
"""

import argparse
import sys
import collections
import json
import socket
import struct
import threading
import time

HOST = "127.0.0.1"


# ------------------------------------------------------------ межі повідомлень

def nadislaty(sock, obj):
    dani = json.dumps(obj, ensure_ascii=False).encode()
    sock.sendall(struct.pack(">I", len(dani)) + dani)


def otrymaty_rivno(sock, n):
    shmatky, zalyshylos = [], n
    while zalyshylos:
        sh = sock.recv(min(zalyshylos, 1 << 16))
        if not sh:
            raise ConnectionError("з'єднання закрито посеред повідомлення")
        shmatky.append(sh)
        zalyshylos -= len(sh)
    return b"".join(shmatky)


def otrymaty(sock):
    golova = sock.recv(4)
    if not golova:
        return None                      # чисте закриття між повідомленнями
    if len(golova) < 4:
        golova += otrymaty_rivno(sock, 4 - len(golova))
    (dovzhyna,) = struct.unpack(">I", golova)
    return json.loads(otrymaty_rivno(sock, dovzhyna).decode())


# --------------------------------------------------------------------- стан

class Broker:
    def __init__(self, pidtverdzhennya, merezha_ms):
        self.pidtverdzhennya = pidtverdzhennya
        self.merezha = merezha_ms / 1000
        self.cherhy = collections.defaultdict(collections.deque)
        self.v_roboti = {}                       # id -> (черга, дані, з'єднання)
        self.pidpysnyky = collections.defaultdict(list)   # тема -> [(сокет, замок)]
        self.umova = threading.Condition()
        self.nastupnyi_id = 1
        self.lich = collections.Counter()

    # --- черги
    def poklasty(self, cherga, dani, na_pochatok=False):
        with self.umova:
            q = self.cherhy[cherga]
            (q.appendleft if na_pochatok else q.append)((self.nastupnyi_id, dani))
            self.nastupnyi_id += 1
            self.lich["покладено"] += 1
            self.umova.notify()

    def vzyaty(self, cherga, chekaty, zyednannia):
        kinets = time.monotonic() + chekaty
        with self.umova:
            while not self.cherhy[cherga]:
                zalyshok = kinets - time.monotonic()
                if zalyshok <= 0:
                    return None
                self.umova.wait(zalyshok)
            mid, dani = self.cherhy[cherga].popleft()
            self.lich["видано"] += 1
            if self.pidtverdzhennya:
                self.v_roboti[mid] = (cherga, dani, zyednannia)
            return mid, dani

    def pidtverdyty(self, mid):
        with self.umova:
            if self.v_roboti.pop(mid, None) is not None:
                self.lich["підтверджено"] += 1

    def povernuty_nepidtverdzheni(self, zyednannia):
        with self.umova:
            svoi = [(mid, z) for mid, z in self.v_roboti.items() if z[2] is zyednannia]
            for mid, (cherga, dani, _) in sorted(svoi, reverse=True):
                del self.v_roboti[mid]
                self.cherhy[cherga].appendleft((mid, dani))
                self.lich["повернуто в чергу"] += 1
            if svoi:
                self.umova.notify_all()
        return len(svoi)

    def ochystyty(self, cherga):
        with self.umova:
            k = len(self.cherhy[cherga])
            self.cherhy[cherga].clear()
            for mid in [m for m, z in self.v_roboti.items() if z[0] == cherga]:
                del self.v_roboti[mid]
            return k

    # --- теми
    def pidpysatys(self, tema, sock):
        with self.umova:
            self.pidpysnyky[tema].append((sock, threading.Lock()))
            return len(self.pidpysnyky[tema])

    def opublikuvaty(self, tema, dani):
        with self.umova:
            spysok = list(self.pidpysnyky[tema])
        dostavleno = 0
        for sock, zamok in spysok:
            try:
                with zamok:
                    nadislaty(sock, {"tema": tema, "dani": dani})
                dostavleno += 1
            except OSError:
                with self.umova:
                    if (sock, zamok) in self.pidpysnyky[tema]:
                        self.pidpysnyky[tema].remove((sock, zamok))
        self.lich["опубліковано"] += 1
        self.lich["доставлено підписникам"] += dostavleno
        return dostavleno

    def stan(self):
        with self.umova:
            return {
                "cherhy": {k: len(v) for k, v in self.cherhy.items()},
                "v_roboti": len(self.v_roboti),
                "pidpysnyky": {k: len(v) for k, v in self.pidpysnyky.items() if v},
                "lichylnyky": dict(self.lich),
                "pidtverdzhennya": self.pidtverdzhennya,
            }


# --------------------------------------------------------------- з'єднання

class Zatrymka:
    """Відповідь «у дорозі»: надсилається через merezha секунд, але брокер тим часом
    уже читає наступний запит — як справжня мережа, де байти летять паралельно."""

    def __init__(self, conn, merezha):
        self.conn, self.merezha = conn, merezha
        self.cherga = collections.deque()
        self.umova = threading.Condition()
        threading.Thread(target=self.vidpravnyk, daemon=True).start()

    def nadislaty(self, obj):
        with self.umova:
            self.cherga.append((time.monotonic() + self.merezha, obj))
            self.umova.notify()

    def vidpravnyk(self):
        while True:
            with self.umova:
                while not self.cherga:
                    self.umova.wait()
                koly, obj = self.cherga.popleft()
            if obj is None:                      # з'єднання закрито — потік більше не потрібен
                return
            pauza = koly - time.monotonic()
            if pauza > 0:
                time.sleep(pauza)
            try:
                nadislaty(self.conn, obj)
            except OSError:
                return


def obsluhovuvaty(conn, adresa, broker):
    zyednannia = object()                 # мітка цього з'єднання для «в роботі»
    slukhach = False                      # підписник: з'єднання лишається відкритим для розсилки
    vidpovidach = Zatrymka(conn, broker.merezha) if broker.merezha else None
    try:
        while True:
            zapyt = otrymaty(conn)
            if zapyt is None:
                break
            dia = zapyt.get("dia")
            if dia == "poklasty":
                broker.poklasty(zapyt["cherga"], zapyt.get("dani"))
                vidpovid = {"ok": True}
            elif dia == "vzyaty":
                rez = broker.vzyaty(zapyt["cherga"], float(zapyt.get("chekaty", 0)), zyednannia)
                if rez is None:
                    vidpovid = {"ok": False, "porozhnio": True}
                else:
                    vidpovid = {"ok": True, "id": rez[0], "dani": rez[1],
                                "treba_pidtverdyty": broker.pidtverdzhennya}
            elif dia == "pidtverdyty":
                broker.pidtverdyty(zapyt["id"])
                vidpovid = {"ok": True}
            elif dia == "opublikuvaty":
                vidpovid = {"ok": True,
                            "otrymuvachiv": broker.opublikuvaty(zapyt["tema"], zapyt.get("dani"))}
            elif dia == "pidpysatys":
                k = broker.pidpysatys(zapyt["tema"], conn)
                print(f"[брокер] новий підписник на «{zapyt['tema']}» — тепер їх {k}")
                slukhach = True
                return                           # далі це з'єднання тільки отримує
            elif dia == "ochystyty":
                vidpovid = {"ok": True, "vydaleno": broker.ochystyty(zapyt["cherga"])}
            elif dia == "stan":
                vidpovid = broker.stan()
            else:
                vidpovid = {"ok": False, "chomu": f"невідома дія {dia!r}"}
            if vidpovidach:
                vidpovidach.nadislaty(vidpovid)
            else:
                nadislaty(conn, vidpovid)
    except (OSError, ValueError) as e:
        if not isinstance(e, ConnectionResetError):
            print(f"[брокер] {adresa[1]}: {type(e).__name__}: {e}")
    finally:
        k = broker.povernuty_nepidtverdzheni(zyednannia)
        if k:
            print(f"[брокер] з'єднання :{adresa[1]} обірвалось — повертаю в чергу "
                  f"непідтверджених: {k}")
        if vidpovidach:
            vidpovidach.nadislaty(None)
        if not slukhach:
            conn.close()


def main():
    sys.stdout.reconfigure(line_buffering=True)   # рядки видно одразу, навіть у перенаправленому виводі
    p = argparse.ArgumentParser(description="брокер: черги й публікація-підписка")
    p.add_argument("--port", type=int, default=50030)
    p.add_argument("--host", default=HOST, help="яку адресу слухати; у контейнері — 0.0.0.0")
    p.add_argument("--pidtverdzhennya", action="store_true",
                   help="повідомлення зникає з черги лише після «pidtverdyty»; "
                        "якщо споживач помер — повертається в чергу")
    p.add_argument("--merezha-ms", type=float, default=0,
                   help="скільки мілісекунд «летить» кожна відповідь (імітація справжньої мережі)")
    args = p.parse_args()

    broker = Broker(args.pidtverdzhennya, args.merezha_ms)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((args.host, args.port))
    s.listen(64)
    rezhym = "з підтвердженням" if args.pidtverdzhennya else "без підтвердження"
    merezha = f" · мережа +{args.merezha_ms:g} мс" if args.merezha_ms else ""
    print(f"[брокер] слухаю {args.host}:{args.port} · {rezhym}{merezha}")
    s.settimeout(0.5)                      # щоб Ctrl+C спрацьовував і на Windows
    try:
        while True:
            try:
                conn, adresa = s.accept()
            except socket.timeout:
                continue
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=obsluhovuvaty, args=(conn, adresa, broker),
                             daemon=True).start()
    except KeyboardInterrupt:
        st = broker.stan()
        print(f"\n[брокер] зупинено · черги {st['cherhy']} · {st['lichylnyky']}")
    finally:
        s.close()


if __name__ == "__main__":
    main()
