"""Координатор двофазної фіксації: один переказ між трьома банками.

    python koordynator_2pc.py                                   # U1 −200, U2 +150, U3 +50
    python koordynator_2pc.py --suma 5000                       # у U1 стільки немає → «ні»
    python koordynator_2pc.py --vpasty pislia-holosuvannia      # упасти між фазами
    python koordynator_2pc.py --vpasty pislia-pershoho-rishennia  # упасти, сказавши рішення лише U1
    python koordynator_2pc.py --vidnovyty                       # після падіння: дочитати журнал і завершити

Фаза 1: усім «підготуйтесь» → кожен голосує «так» або «ні».
Фаза 2: усі «так» → «фіксуємо»; хоч одне «ні» або мовчання → «скасовуємо».
Рішення координатор записує у zhurnal-koordynatora.txt ДО того, як розсилати.
"""

import argparse
import json
import os
import sys
import time
import uuid

from uchasnyk import UCHASNYKY, zapyt

ZHURNAL = "zhurnal-koordynatora.txt"


def chas(t0):
    return f"{(time.perf_counter() - t0) * 1000:6.0f} мс"


def pysaty(zapys):
    with open(ZHURNAL, "a", encoding="utf-8") as f:
        f.write(json.dumps(zapys, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def rozislaty(tx, rishennia, komu, t0):
    dia = "zafiksuvaty" if rishennia == "zafiksovano" else "skasuvaty"
    for imya in komu:
        try:
            zapyt(UCHASNYKY[imya], {"dia": dia, "tx": tx})
            print(f"{chas(t0)}  → {imya}: {dia}")
        except OSError as e:
            print(f"{chas(t0)}  → {imya}: недоступний ({type(e).__name__}) — доведеться повторити")


def tranzaktsiia(args):
    tx = "T-" + uuid.uuid4().hex[:4]
    delty = {"U1": -args.suma, "U2": args.suma * 3 // 4, "U3": args.suma - args.suma * 3 // 4}
    t0 = time.perf_counter()
    print(f"{chas(t0)}  транзакція {tx}: " + ", ".join(f"{k} {v:+d}" for k, v in delty.items()))
    pysaty({"tx": tx, "podiya": "pochatok", "delty": delty})

    # ---- фаза 1
    holosy = {}
    for imya, delta in delty.items():
        try:
            v = zapyt(UCHASNYKY[imya], {"dia": "pidhotuvatysia", "tx": tx, "delta": delta}, taimaut=3)
            holosy[imya] = v["holos"]
        except OSError as e:
            holosy[imya] = f"мовчить ({type(e).__name__})"
        print(f"{chas(t0)}  ← {imya}: {holosy[imya]}")

    if args.vpasty == "pislia-holosuvannia":
        print(f"{chas(t0)}  💥 координатор падає: голоси зібрано, рішення ніхто не почув")
        os._exit(1)

    # ---- фаза 2
    rishennia = "zafiksovano" if all(h == "tak" for h in holosy.values()) else "skasovano"
    pysaty({"tx": tx, "podiya": "rishennia", "rishennia": rishennia})
    print(f"{chas(t0)}  рішення: {'ФІКСУЄМО' if rishennia == 'zafiksovano' else 'СКАСОВУЄМО'} (записано в журнал)")
    komu = [i for i in delty if holosy.get(i) == "tak" or rishennia == "zafiksovano"]
    if args.vpasty == "pislia-pershoho-rishennia":
        rozislaty(tx, rishennia, komu[:1], t0)
        print(f"{chas(t0)}  💥 координатор падає: рішення почув лише {komu[0]}")
        os._exit(1)
    rozislaty(tx, rishennia, komu, t0)
    pysaty({"tx": tx, "podiya": "kinets"})
    print(f"{chas(t0)}  готово")


def vidnovyty():
    """Дочитати журнал: що почали, але не закінчили."""
    if not os.path.exists(ZHURNAL):
        sys.exit("журналу координатора немає — відновлювати нічого")
    tx_stan = {}
    with open(ZHURNAL, encoding="utf-8") as f:
        for r in f:
            z = json.loads(r)
            s = tx_stan.setdefault(z["tx"], {"delty": None, "rishennia": None, "kinets": False})
            if z["podiya"] == "pochatok":
                s["delty"] = z["delty"]
            elif z["podiya"] == "rishennia":
                s["rishennia"] = z["rishennia"]
            elif z["podiya"] == "kinets":
                s["kinets"] = True
    t0 = time.perf_counter()
    nezaversheni = {tx: s for tx, s in tx_stan.items() if not s["kinets"]}
    if not nezaversheni:
        print("усі транзакції в журналі завершені")
    for tx, s in nezaversheni.items():
        if s["rishennia"] is None:
            s["rishennia"] = "skasovano"
            pysaty({"tx": tx, "podiya": "rishennia", "rishennia": "skasovano"})
            print(f"{tx}: рішення в журналі немає → СКАСОВУЄМО (ніхто не міг його почути)")
        else:
            print(f"{tx}: у журналі рішення «{s['rishennia']}» → розсилаю всім ще раз")
        rozislaty(tx, s["rishennia"], list(s["delty"]), t0)
        pysaty({"tx": tx, "podiya": "kinets"})


def main():
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser()
    p.add_argument("--suma", type=int, default=200, help="скільки знімається з U1")
    p.add_argument("--vpasty", choices=["pislia-holosuvannia", "pislia-pershoho-rishennia"])
    p.add_argument("--vidnovyty", action="store_true", help="завершити те, що лишилось у журналі")
    args = p.parse_args()
    if args.vidnovyty:
        vidnovyty()
    else:
        tranzaktsiia(args)


if __name__ == "__main__":
    main()
