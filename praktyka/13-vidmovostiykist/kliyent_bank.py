"""Клієнт трьох банків: подивитись стан і спробувати звичайну операцію.

    python kliyent_bank.py stan           # залишки, хто заблокований, загальна сума
    python kliyent_bank.py znyaty U1 50   # зняти готівку з рахунку в U1
    python kliyent_bank.py rozpytaty T-1a2b   # ⭐: що кожен учасник знає про транзакцію
"""

import argparse
import sys

from uchasnyk import POCHATKOVYI, UCHASNYKY, zapyt


def main():
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser()
    p.add_argument("dia", choices=["stan", "znyaty", "rozpytaty"])
    p.add_argument("arg", nargs="*")
    a = p.parse_args()

    if a.dia == "stan":
        suma = 0
        for imya, port in UCHASNYKY.items():
            try:
                s = zapyt(port, {"dia": "stan"})
            except OSError:
                print(f"{imya}: недоступний")
                suma = None
                continue
            if suma is not None:
                suma += s["zalyshok"]
            g = s["gotovyi"]
            stan = (f"🔒 ГОТОВИЙ по {g['tx']} ({g['delta']:+d}) уже {g['sekund']} с — рахунок заблоковано"
                    if g else "вільний")
            print(f"{imya}: {s['zalyshok']:>5} грн · {stan}")
        chekaiut = any(zapyt(p, {"dia": "stan"})["gotovyi"] for p in UCHASNYKY.values()) if suma is not None else False
        if suma is not None:
            ochikuvano = POCHATKOVYI * len(UCHASNYKY)
            print(f"разом: {suma} грн " + ("✔ гроші ніде не з'явились і не зникли" if suma == ochikuvano
                                         else f"⏳ має бути {ochikuvano}: хтось іще чекає рішення" if chekaiut
                                         else f"❌ має бути {ochikuvano} — атомарність порушено"))
    elif a.dia == "znyaty":
        imya, suma = a.arg[0], int(a.arg[1])
        v = zapyt(UCHASNYKY[imya], {"dia": "operatsiia", "delta": -suma})
        print(f"✔ {imya}: знято {suma}, залишок {v['zalyshok']}" if v["ok"] else f"❌ {imya}: {v['chomu']}")
    elif a.dia == "rozpytaty":
        tx = a.arg[0]
        for imya, port in UCHASNYKY.items():
            try:
                s = zapyt(port, {"dia": "stan"})
            except OSError:
                print(f"{imya}: недоступний")
                continue
            if tx in s["rishennia"]:
                znaie = f"знає рішення: {s['rishennia'][tx]}"
            elif s["gotovyi"] and s["gotovyi"]["tx"] == tx:
                znaie = "проголосував «так», рішення не знає"
            else:
                znaie = "про цю транзакцію нічого не знає"
            print(f"{imya}: {znaie}")


if __name__ == "__main__":
    main()
