"""Запускач багатовузлового стенда — те, що робить `docker compose`, але процесами.

    python zapuskach.py up                  # підняти всі вузли зі stend.json і стежити за ними
    python zapuskach.py stan                # (з іншого термінала) що з кожним вузлом
    python zapuskach.py stop P2             # убити вузол — як висмикнути кабель живлення
    python zapuskach.py pauza P2 5          # заморозити на 5 с — вузол живий, але мовчить
    python zapuskach.py vymknuty P2         # зупинити й НЕ перезапускати
    python zapuskach.py uvimknuty P2        # повернути вимкнений
    python zapuskach.py down                # зупинити всі вузли й сам запускач

Відповідність до Docker:
    up              ↔ docker compose up
    stop            ↔ docker kill (а "perezapusk": true — це restart: always)
    pauza           ↔ docker pause / unpause
    vymknuty        ↔ docker compose stop
    down            ↔ docker compose down
    "pislia"        ↔ depends_on

Конфігурація — stend.json поруч (або --konfig). Журнали вузлів — у теці zhurnaly/.
Зупинити все — Ctrl+C у терміналі, де запущено `up`.
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time

HOST = "127.0.0.1"
PORT_KERUVANNIA = 50090


# ------------------------------------------------------------ заморозити процес

def zamorozyty(p):
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x0800, False, p.pid)   # PROCESS_SUSPEND_RESUME
        ctypes.windll.ntdll.NtSuspendProcess(h)
        ctypes.windll.kernel32.CloseHandle(h)
    else:
        os.kill(p.pid, signal.SIGSTOP)


def rozmorozyty(p):
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x0800, False, p.pid)
        ctypes.windll.ntdll.NtResumeProcess(h)
        ctypes.windll.kernel32.CloseHandle(h)
    else:
        os.kill(p.pid, signal.SIGCONT)


# ------------------------------------------------------------ вузол

class Vuzol:
    def __init__(self, opys, teka):
        self.imya = opys["imya"]
        self.komanda = opys["komanda"]
        self.perezapusk = opys.get("perezapusk", True)
        self.pislia = opys.get("pislia")
        self.zatrymka = opys.get("zatrymka", 0.0)
        self.teka = teka
        self.p = None
        self.stan = "ще не запущено"
        self.perezapuskiv = 0
        self.zapushcheno_o = None
        self.vymknuto = False
        self.zamorozheno_do = 0.0

    def zapustyty(self):
        os.makedirs(os.path.join(self.teka, "zhurnaly"), exist_ok=True)
        log = open(os.path.join(self.teka, "zhurnaly", f"{self.imya}.log"), "a", encoding="utf-8")
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        self.p = subprocess.Popen([sys.executable] + self.komanda, cwd=self.teka, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                  encoding="utf-8", errors="replace")
        self.stan = "працює"
        self.zapushcheno_o = time.monotonic()
        threading.Thread(target=self.chytaty_vyvid, args=(self.p, log), daemon=True).start()

    def chytaty_vyvid(self, p, log):
        for ryadok in p.stdout:
            log.write(ryadok)
            log.flush()
            print(f"  {self.imya:>8} │ {ryadok.rstrip()}", flush=True)
        log.close()


class Zapuskach:
    def __init__(self, konfig):
        teka = os.path.dirname(os.path.abspath(konfig))
        with open(konfig, encoding="utf-8") as f:
            self.vuzly = {v["imya"]: Vuzol(v, teka) for v in json.load(f)["vuzly"]}
        self.zamok = threading.Lock()
        self.pochatok = time.monotonic()
        self.zupyniaiemo = False

    def druk(self, tekst):
        print(f"[запускач {time.monotonic() - self.pochatok:6.1f} с] {tekst}", flush=True)

    def up(self):
        for v in self.vuzly.values():
            if v.pislia:
                time.sleep(v.zatrymka)
            v.zapustyty()
            self.druk(f"{v.imya} запущено (pid {v.p.pid})" + (f", після {v.pislia}" if v.pislia else ""))

    def storozh(self):
        """restart: always — перезапускати впалі вузли."""
        while True:
            time.sleep(0.2)
            with self.zamok:
                if self.zupyniaiemo:
                    return
                for v in self.vuzly.values():
                    if v.p is None or v.vymknuto:
                        continue
                    if v.zamorozheno_do and time.monotonic() >= v.zamorozheno_do:
                        rozmorozyty(v.p)
                        v.zamorozheno_do = 0.0
                        v.stan = "працює"
                        self.druk(f"{v.imya} розморожено")
                    kod = v.p.poll()
                    if kod is not None and v.stan != "мертвий":
                        zhyv = time.monotonic() - v.zapushcheno_o
                        v.stan = "мертвий"
                        self.druk(f"{v.imya} завершився (код {kod}) після {zhyv:.1f} с роботи"
                                  + (" — перезапущу через 1 с" if v.perezapusk else ""))
                        v.pomer_o = time.monotonic()
                    if v.stan == "мертвий" and v.perezapusk and time.monotonic() - v.pomer_o >= 1.0:
                        v.perezapuskiv += 1
                        v.zapustyty()
                        self.druk(f"{v.imya} перезапущено (раз {v.perezapuskiv}), без нього було "
                                  f"{time.monotonic() - v.pomer_o:.1f} с")

    def komanda(self, z):
        dia, imya = z.get("dia"), z.get("imya")
        with self.zamok:
            if dia == "stan":
                rez = []
                for v in self.vuzly.values():
                    pratsiuie = time.monotonic() - v.zapushcheno_o if v.zapushcheno_o else 0
                    rez.append({"imya": v.imya, "pid": v.p.pid if v.p else None, "stan": v.stan,
                                "perezapuskiv": v.perezapuskiv, "sekund": round(pratsiuie, 1)})
                return {"ok": True, "vuzly": rez}
            if dia == "down":
                self.druk("down: зупиняю всі вузли")
                self.zupynyty_vse()
                threading.Timer(0.3, os._exit, args=(0,)).start()
                return {"ok": True}
            v = self.vuzly.get(imya)
            if not v:
                return {"ok": False, "chomu": f"вузла {imya!r} немає; є {', '.join(self.vuzly)}"}
            if dia == "stop":
                v.p.kill()
                self.druk(f"✂ {imya}: убито командою stop")
                return {"ok": True}
            if dia == "pauza":
                zamorozyty(v.p)
                v.zamorozheno_do = time.monotonic() + float(z.get("sekund", 5))
                v.stan = "заморожено"
                self.druk(f"❄ {imya}: заморожено на {z.get('sekund', 5)} с — процес живий, з'єднання відкриті")
                return {"ok": True}
            if dia == "vymknuty":
                v.vymknuto = True
                v.p.kill()
                v.stan = "вимкнено"
                self.druk(f"⏻ {imya}: вимкнено, перезапуску не буде")
                return {"ok": True}
            if dia == "uvimknuty":
                v.vymknuto = False
                v.zapustyty()
                self.druk(f"⏻ {imya}: увімкнено знову")
                return {"ok": True}
        return {"ok": False, "chomu": f"невідома команда {dia!r}"}

    def keruvannia(self):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT_KERUVANNIA))
        s.listen(8)
        while True:
            conn, _ = s.accept()
            try:
                f = conn.makefile("rwb")
                r = f.readline()
                f.write((json.dumps(self.komanda(json.loads(r.decode())), ensure_ascii=False) + "\n").encode())
                f.flush()
            except (OSError, ValueError):
                pass
            finally:
                conn.close()

    def zupynyty_vse(self):
        self.zupyniaiemo = True
        for v in self.vuzly.values():
            if v.p and v.p.poll() is None:
                if v.zamorozheno_do:
                    rozmorozyty(v.p)
                v.p.kill()


def nadislaty(z):
    try:
        s = socket.create_connection((HOST, PORT_KERUVANNIA), timeout=3)
    except OSError:
        sys.exit("запускач не працює — спершу `python zapuskach.py up` в іншому терміналі")
    f = s.makefile("rwb")
    f.write((json.dumps(z, ensure_ascii=False) + "\n").encode())
    f.flush()
    v = json.loads(f.readline().decode())
    s.close()
    return v


def main():
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser()
    p.add_argument("dia", choices=["up", "stan", "stop", "pauza", "vymknuty", "uvimknuty", "down"])
    p.add_argument("imya", nargs="?")
    p.add_argument("sekund", nargs="?", type=float, default=5)
    p.add_argument("--konfig", default="stend.json")
    a = p.parse_args()

    if a.dia == "up":
        z = Zapuskach(a.konfig)
        threading.Thread(target=z.keruvannia, daemon=True).start()
        z.up()
        threading.Thread(target=z.storozh, daemon=True).start()
        z.druk(f"стенд піднято: {', '.join(z.vuzly)} · керування — `python zapuskach.py stan|stop|pauza …`")
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            z.druk("зупиняю всі вузли")
            z.zupynyty_vse()
        return
    if a.dia == "stan":
        v = nadislaty({"dia": "stan"})
        print(f"{'вузол':<10}{'pid':>7}  {'стан':<14}{'перезапусків':>13}{'працює, с':>11}")
        for u in v["vuzly"]:
            print(f"{u['imya']:<10}{u['pid'] or '—':>7}  {u['stan']:<14}{u['perezapuskiv']:>13}{u['sekund']:>11}")
        return
    if not a.imya and a.dia != "down":
        sys.exit("кому? наприклад: python zapuskach.py stop P2")
    v = nadislaty({"dia": a.dia, "imya": a.imya, "sekund": a.sekund})
    print("✔" if v["ok"] else f"❌ {v['chomu']}")


if __name__ == "__main__":
    main()
