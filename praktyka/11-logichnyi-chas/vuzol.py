"""Вузол «чату на три вузли»: годинник, що розходиться, логічний час і вибори координатора.

    python vuzol.py --imya A
    python vuzol.py --imya B
    python vuzol.py --imya C

Порядок запуску — будь-який: вузли спершу дочекаються одне одного.

Що робить:
  1. Один раз розігрує розмову (питання → відповідь → уточнення → «домовились»)
     плюс кілька подій, ні від чого не залежних. Кожну подію пише в zhurnal-<ім'я>.jsonl
     з ДВОМА часами: фізичним (годинник вузла, що розходиться) і логічним (godynnyk.py).
  2. Увесь час обирає координатора алгоритмом задираки: координатор раз на
     --puls с шле «пульс»; хто не чув його --taimaut с — починає вибори.

Годинники розходяться навмисно, як у житті: A — точний, B відстає на 0,3 с,
C поспішає на 0,2 с. Змінити — --zsuv.

    python vuzol.py --imya C --tilky-vybory      # перезапуск без повтору розмови
    python vuzol.py --imya C --zavmerty 6        # ⭐3: на 6-й секунді завмерти на 3 с
    python vuzol.py --imya C --drizhannia 0.4    # ⭐2: пульс запізнюється на 0…0,4 с

Повідомлення — UDP-датаграми з JSON: межі повідомлень є самі собою, гарантій доставки немає.
Зупинити — Ctrl+C.
"""

import argparse
import json
import random
import socket
import sys
import threading
import time

from godynnyk import Lamport, Vektornyi

HOST = "127.0.0.1"
VUZLY = {"A": (1, 50041, 0.0), "B": (2, 50042, -0.3), "C": (3, 50043, 0.2)}   # номер, порт, зсув годинника


class Vuzol:
    def __init__(self, args):
        self.imya = args.imya
        self.nomer, self.port, zsuv = VUZLY[args.imya]
        self.zsuv = zsuv if args.zsuv is None else args.zsuv
        self.susidy = {i: v for i, v in VUZLY.items() if i != self.imya}
        self.args = args
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((HOST, self.port))
        self.sock.settimeout(0.2)
        self.zamok = threading.RLock()
        self.L = Lamport()
        self.V = Vektornyi(sorted(VUZLY), self.imya)
        self.lich = 0
        self.zhurnal = None if args.tilky_vybory else open(f"zhurnal-{self.imya}.jsonl", "w", encoding="utf-8")
        self.znayu = set()                          # кого вже чув (рукостискання)
        self.pochatok = time.monotonic()
        self.pauza_do = 0.0
        # вибори
        self.koordynator = None
        self.ostannii_puls = time.monotonic()
        self.vybory = False
        self.vybory_pochatok = 0.0
        self.ok_do = 0.0
        self.ok_bulo = False
        self.zmin_koordynatora = 0

    # ------------------------------------------------------------ службове
    def fiz(self):
        """Фізичний годинник ЦЬОГО вузла — справжній час плюс зсув."""
        return time.time() + self.zsuv

    def druk(self, tekst):
        t = time.monotonic() - self.pochatok
        print(f"[{self.imya} {t:6.2f} с] {tekst}", flush=True)

    def slaty(self, kudy, povidomlennia):
        dani = json.dumps(povidomlennia, ensure_ascii=False).encode()
        self.sock.sendto(dani, (HOST, self.susidy[kudy][1]))

    def slaty_vsim(self, povidomlennia):
        for i in self.susidy:
            self.slaty(i, povidomlennia)

    def zapysaty(self, vyd, tekst, L, V, **dodatkovo):
        self.lich += 1
        pid = f"{self.imya}{self.lich}"
        zapys = {"id": pid, "vuzol": self.imya, "vyd": vyd, "tekst": tekst,
                 "fiz": round(self.fiz(), 4), "L": L, "V": V, **dodatkovo}
        if self.zhurnal:
            self.zhurnal.write(json.dumps(zapys, ensure_ascii=False) + "\n")
            self.zhurnal.flush()
        strilka = {"vlasna": "•", "nadislano": "→", "otrymano": "←"}[vyd]
        self.druk(f"{pid:<4} {strilka} L={L:<3} {tekst}")
        return pid

    # ------------------------------------------------------------ події чату
    def vlasna(self, tekst):
        with self.zamok:
            return self.zapysaty("vlasna", tekst, self.L.vlasna_podiya(), self.V.vlasna_podiya())

    def nadislaty_chat(self, tekst):
        with self.zamok:
            L, V = self.L.pered_nadsylanniam(), self.V.pered_nadsylanniam()
            pid = self.zapysaty("nadislano", tekst, L, V)
            self.slaty_vsim({"t": "chat", "vid": self.imya, "id": pid, "tekst": tekst, "L": L, "V": V})

    def otrymaty_chat(self, m):
        with self.zamok:
            pid = self.zapysaty("otrymano", f"від {m['vid']}: {m['tekst']}",
                                self.L.pislia_otrymannia(m["L"]), self.V.pislia_otrymannia(m["V"]),
                                prychyna=m["id"])
        # реакції — уже поза замком і з крихітною «думкою», як у людини
        tekst = m["tekst"]
        if self.imya == "B" and tekst.startswith("Питання"):
            time.sleep(0.05)
            self.vlasna("подумав, хто вільний")
            self.nadislaty_chat("Відповідь: беру рядки 0–399")
        elif self.imya == "C" and tekst.startswith("Відповідь"):
            time.sleep(0.05)
            self.nadislaty_chat("Тоді я — рядки 400–799")
        elif self.imya == "A" and tekst.startswith("Тоді я"):
            time.sleep(0.05)
            self.nadislaty_chat("Домовились, починаємо")

    def rozmova(self):
        """Сценарій, однаковий для всіх запусків. Час — від моменту, коли всі одне одного почули."""
        start = time.monotonic()

        def chekaty_do(t):
            time.sleep(max(0.0, start + t - time.monotonic()))

        if self.imya == "A":
            chekaty_do(0.3)
            self.vlasna("прочитав завдання")
            chekaty_do(0.7)
            self.nadislaty_chat("Питання: хто бере рядки 0–399?")
        elif self.imya == "B":
            chekaty_do(0.2)
            self.vlasna("відкрив чат")
        elif self.imya == "C":
            chekaty_do(0.4)
            self.vlasna("запустив обчислення")
        chekaty_do(2.0 + 0.1 * self.nomer)
        self.nadislaty_chat("статус: живий")
        chekaty_do(3.0)
        self.druk("розмову закінчено — журнал zhurnal-%s.jsonl. Далі — лише вибори." % self.imya)

    # ------------------------------------------------------------ вибори
    def pochaty_vybory(self, chomu):
        with self.zamok:
            if self.vybory:
                return
            self.vybory = True
            self.vybory_pochatok = time.monotonic()
            self.ok_bulo = False
            self.ok_do = time.monotonic() + 0.5
            vyshchi = [i for i, v in self.susidy.items() if v[0] > self.nomer]
        self.druk(f"вибори: {chomu} → питаю старших: {', '.join(vyshchi) or 'старших немає'}")
        for i in vyshchi:
            self.slaty(i, {"t": "vybory", "vid": self.imya, "nomer": self.nomer})

    def staty_koordynatorom(self):
        with self.zamok:
            bulo = self.koordynator
            self.koordynator = self.imya
            self.vybory = False
            prostii = time.monotonic() - self.ostannii_puls
            self.ostannii_puls = time.monotonic()
        if bulo != self.imya:
            self.zmin_koordynatora += 1
            self.druk(f"★ я — координатор (без координатора було {prostii:.2f} с)" if bulo is None
                      else f"★ я — координатор (замість {bulo})")
        self.slaty_vsim({"t": "koordynator", "vid": self.imya, "nomer": self.nomer})

    def pryiniaty_koordynatora(self, imya):
        with self.zamok:
            bulo = self.koordynator
            self.koordynator = imya
            self.vybory = False
            prostii = time.monotonic() - self.ostannii_puls
            self.ostannii_puls = time.monotonic()
        if bulo != imya:
            self.zmin_koordynatora += 1
            if bulo is None:
                self.druk(f"координатор тепер {imya} (без координатора було {prostii:.2f} с)")
            else:
                self.druk(f"координатор тепер {imya} (замість {bulo})")
        if VUZLY[imya][0] < self.nomer:              # молодший оголосив себе — задираємо
            self.pochaty_vybory(f"{imya} молодший за мене")

    def tsykl_vyboriv(self):
        while True:
            time.sleep(0.05)
            if time.monotonic() < self.pauza_do:
                continue
            if self.pauza_do and not getattr(self, "_prokynuvsia", False):
                self._prokynuvsia = True
                self.druk("прокинувся — і досі вважаю себе координатором")
            teper = time.monotonic()
            with self.zamok:
                ja_koord = self.koordynator == self.imya
                koord, vybory = self.koordynator, self.vybory
            if ja_koord:
                if teper - getattr(self, "_ostannii_vidpravlenyi", 0) >= self.args.puls:
                    if self.args.drizhannia:
                        time.sleep(random.uniform(0, self.args.drizhannia))
                    self.slaty_vsim({"t": "puls", "vid": self.imya, "nomer": self.nomer})
                    self._ostannii_vidpravlenyi = time.monotonic()
                if self.args.zavmerty and teper - self.pochatok >= self.args.zavmerty \
                        and not getattr(self, "_vzhe_zavmyrav", False):
                    self._vzhe_zavmyrav = True
                    self.druk("❄ завмираю на 3 с (як збирач сміття чи перевантажений диск) — "
                              "але й далі вважаю себе координатором")
                    self.pauza_do = time.monotonic() + 3.0
                continue
            if vybory:
                if not self.ok_bulo and teper > self.ok_do:
                    self.staty_koordynatorom()
                elif self.ok_bulo and teper - self.vybory_pochatok > 2 * self.args.taimaut + 0.5:
                    with self.zamok:
                        self.vybory = False
                    self.pochaty_vybory("старший відповів, але координатора так і не оголосив")
                continue
            if koord is None:
                self.pochaty_vybory("координатора ще немає")
            elif teper - self.ostannii_puls > self.args.taimaut:
                with self.zamok:
                    self.koordynator = None
                self.druk(f"координатор {koord} мовчить {teper - self.ostannii_puls:.2f} с")
                self.pochaty_vybory(f"{koord} мовчить")

    # ------------------------------------------------------------ приймання
    def tsykl_pryiomu(self):
        while True:
            if time.monotonic() < self.pauza_do:
                time.sleep(0.05)                      # пакети тим часом чекають у буфері ОС
                continue
            try:
                dani, _ = self.sock.recvfrom(65536)
            except socket.timeout:
                continue
            except ConnectionResetError:              # Windows: сусід закритий — для UDP це не помилка
                continue
            m = json.loads(dani.decode())
            t = m["t"]
            if t == "pryvit":
                self.znayu.add(m["vid"])
                if m.get("zapyt"):                    # відповідаємо завжди — і перезапущеному теж
                    self.slaty(m["vid"], {"t": "pryvit", "vid": self.imya, "zapyt": False})
            elif t == "chat":
                threading.Thread(target=self.otrymaty_chat, args=(m,), daemon=True).start()
            elif t == "vybory":
                self.slaty(m["vid"], {"t": "ok", "vid": self.imya})
                if self.koordynator == self.imya:
                    self.slaty_vsim({"t": "koordynator", "vid": self.imya, "nomer": self.nomer})
                else:
                    self.pochaty_vybory(f"{m['vid']} оголосив вибори, а я старший")
            elif t == "ok":
                self.ok_bulo = True
            elif t in ("koordynator", "puls"):
                with self.zamok:
                    koord = self.koordynator
                    if koord == m["vid"]:
                        self.ostannii_puls = time.monotonic()
                if (koord not in (None, self.imya, m["vid"])
                        and VUZLY[m["vid"]][0] < VUZLY[koord][0]):
                    continue                          # молодший, поки старший координатор не мовчить
                if koord != m["vid"]:
                    if self.koordynator == self.imya and m["nomer"] < self.nomer:
                        self.slaty_vsim({"t": "koordynator", "vid": self.imya, "nomer": self.nomer})
                    else:
                        if self.koordynator == self.imya:
                            self.druk(f"старший {m['vid']} живий — віддаю координацію")
                        self.pryiniaty_koordynatora(m["vid"])

    # ------------------------------------------------------------ запуск
    def ruky(self):
        """Рукостискання: вітаємось, доки не почуємо обох сусідів."""
        self.druk(f"порт {self.port} · мій годинник {self.zsuv:+.3f} с від справжнього · "
                  f"чекаю сусідів {', '.join(self.susidy)}…")
        while len(self.znayu) < len(self.susidy):
            self.slaty_vsim({"t": "pryvit", "vid": self.imya, "zapyt": True})
            time.sleep(0.3)
        self.druk("усі на зв'язку")


def main():
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser()
    p.add_argument("--imya", choices=sorted(VUZLY), required=True)
    p.add_argument("--zsuv", type=float, default=None, help="зсув фізичного годинника, с")
    p.add_argument("--puls", type=float, default=0.5, help="як часто координатор шле пульс, с")
    p.add_argument("--taimaut", type=float, default=1.5, help="скільки мовчання вважати смертю, с")
    p.add_argument("--tilky-vybory", action="store_true", help="не розігрувати розмову, журнал не писати")
    p.add_argument("--zavmerty", type=float, default=0, help="⭐3: на цій секунді завмерти на 3 с")
    p.add_argument("--drizhannia", type=float, default=0, help="⭐2: випадкове запізнення пульсу, с")
    args = p.parse_args()

    v = Vuzol(args)
    threading.Thread(target=v.tsykl_pryiomu, daemon=True).start()
    try:
        v.ruky()
        threading.Thread(target=v.tsykl_vyboriv, daemon=True).start()
        if not args.tilky_vybory:
            threading.Thread(target=v.rozmova, daemon=True).start()
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        v.druk(f"зупинено · координатор змінювався {v.zmin_koordynatora} раз(и)")


if __name__ == "__main__":
    main()
