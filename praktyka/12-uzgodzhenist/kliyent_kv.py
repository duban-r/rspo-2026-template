"""Клієнт трьох реплік: писати, читати, міряти вікно неузгодженості, рвати мережу.

    python kliyent_kv.py dodaty zamiry "Петренко: 3.2 с" --do R1        # додати запис у журнал
    python kliyent_kv.py dodaty zamiry "Іваненко: 4.1 с" --do R3 --W 2  # з кворумом запису
    python kliyent_kv.py chytaty zamiry --z R3                          # прочитати з однієї копії
    python kliyent_kv.py chytaty zamiry --z R1 --R 2                    # з кворумом читання
    python kliyent_kv.py stan                                           # що лежить у кожній копії
    python kliyent_kv.py vikno --do R1 --z R3 --raz 10                  # вікно неузгодженості
    python kliyent_kv.py rozryv R3                                      # відрізати R3 від решти
    python kliyent_kv.py zyednaty                                       # відновити зв'язок
"""

import argparse
import statistics
import sys
import time

from replika import REPLIKY, zapyt


def port(imya):
    return REPLIKY[imya][0]


def opysaty(versiya):
    if versiya is None:
        return "— (ключа немає)"
    z = versiya["znach"]
    if isinstance(z, list):
        teksty = "; ".join(f"{e['tekst']} [{e['vuzol']}]" for e in z)
        return f"{len(z)} зап.: {teksty}"
    return repr(z)


def main():
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser()
    p.add_argument("dia", choices=["zapysaty", "dodaty", "chytaty", "stan", "vikno", "rozryv", "zyednaty"])
    p.add_argument("arg", nargs="*", help="ключ і значення / кого відрізати")
    p.add_argument("--do", default="R1", help="на яку репліку писати")
    p.add_argument("--z", default="R1", help="з якої репліки читати")
    p.add_argument("--W", type=int, default=1, help="скільки копій мають підтвердити запис")
    p.add_argument("--R", type=int, default=1, help="зі скількох копій читати")
    p.add_argument("--raz", type=int, default=10, help="vikno: скільки разів міряти")
    a = p.parse_args()

    if a.dia in ("zapysaty", "dodaty"):
        kliuch, znach = a.arg[0], " ".join(a.arg[1:])
        t0 = time.perf_counter()
        v = zapyt(port(a.do), {"dia": a.dia, "kliuch": kliuch, "znach": znach, "W": a.W}, taimaut=6)
        dt = (time.perf_counter() - t0) * 1000
        if v["ok"]:
            print(f"✔ {a.do}, W={a.W}, за {dt:.0f} мс → {opysaty(v['versiya'])}")
        else:
            print(f"❌ {a.do}, W={a.W}, за {dt:.0f} мс: {v['chomu']}")
    elif a.dia == "chytaty":
        t0 = time.perf_counter()
        v = zapyt(port(a.z), {"dia": "chytaty", "kliuch": a.arg[0], "R": a.R}, taimaut=6)
        dt = (time.perf_counter() - t0) * 1000
        if v["ok"]:
            print(f"{'+'.join(v['vid'])}, R={a.R}, за {dt:.0f} мс → {opysaty(v['versiya'])}")
        else:
            print(f"❌ {a.z}, R={a.R}, за {dt:.0f} мс: {v['chomu']}")
    elif a.dia == "stan":
        for imya in REPLIKY:
            try:
                st = zapyt(port(imya), {"dia": "stan"})
                rozryv = f" · ✂ без зв'язку з {', '.join(st['rozirvano'])}" if st["rozirvano"] else ""
                print(f"{imya}{rozryv}")
                for k, v in sorted(st["dani"].items()):
                    print(f"   {k}: {opysaty(v)}")
                if not st["dani"]:
                    print("   (порожньо)")
            except OSError:
                print(f"{imya}: недоступна")
    elif a.dia == "vikno":
        kliuch = "vikno-test"
        vikna = []
        for i in range(a.raz):
            znach = f"значення {i} · {time.time():.3f}"
            t0 = time.perf_counter()
            v = zapyt(port(a.do), {"dia": "zapysaty", "kliuch": kliuch, "znach": znach})
            if not v["ok"]:
                sys.exit(f"запис не вдався: {v['chomu']}")
            while True:
                r = zapyt(port(a.z), {"dia": "chytaty", "kliuch": kliuch})
                if r["versiya"] and r["versiya"]["znach"] == znach:
                    break
                if time.perf_counter() - t0 > 5:
                    sys.exit(f"за 5 с {a.z} так і не побачив запису — розрив?")
                time.sleep(0.002)
            vikna.append((time.perf_counter() - t0) * 1000)
        print(f"вікно {a.do} → {a.z}, {a.raz} разів: медіана {statistics.median(vikna):.0f} мс · "
              f"мін {min(vikna):.0f} · макс {max(vikna):.0f}")
    elif a.dia == "rozryv":
        vidrizani = set(a.arg)
        reshta = set(REPLIKY) - vidrizani
        for imya in REPLIKY:
            z = reshta if imya in vidrizani else vidrizani
            zapyt(port(imya), {"dia": "rozryv", "z": sorted(z)})
        print(f"✂ {' + '.join(sorted(vidrizani))} | {' + '.join(sorted(reshta))} — зв'язку між ними немає")
    elif a.dia == "zyednaty":
        for imya in REPLIKY:
            zapyt(port(imya), {"dia": "zyednaty"})
        print("🔗 зв'язок відновлено; репліки обмінюються даними (зачекайте ~1 с і дивіться `stan`)")


if __name__ == "__main__":
    main()
