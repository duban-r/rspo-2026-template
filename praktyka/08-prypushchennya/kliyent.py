"""Клієнт служби «журнал замірів».

За замовчуванням написаний **наївно** — рівно так, як пишуть, поки мережа
не підвела жодного разу: без таймауту, без повторів, без ключа.
Прапорцями вмикаються виправлення — по одному, щоб було видно, що дає кожне.

    python kliyent.py                          # наївно, напряму до служби
    python kliyent.py --port 50010             # через ненадійну мережу
    python kliyent.py --port 50010 --taimaut 2
    python kliyent.py --port 50010 --taimaut 2 --sprob 4
    python kliyent.py --port 50010 --taimaut 2 --sprob 4 --kliuch

Наприкінці клієнт питає службу, скільки записів вона насправді нарахувала,
і порівнює з тим, скільки надіслав. Розбіжність — і є те, що ви шукаєте.
"""

import argparse
import json
import socket
import time
import uuid

HOST = "127.0.0.1"


def poslaty(port, zapyt, taimaut):
    """Одна спроба: з'єднатись, надіслати рядок, дочекатись рядка у відповідь."""
    s = socket.create_connection((HOST, port), timeout=taimaut)
    try:
        if taimaut:
            s.settimeout(taimaut)
        f = s.makefile("rwb")
        f.write((json.dumps(zapyt, ensure_ascii=False) + "\n").encode())
        f.flush()
        ryadok = f.readline()
        if not ryadok:
            raise ConnectionError("з'єднання закрито без відповіді")
        return json.loads(ryadok.decode())
    finally:
        s.close()


def poslaty_z_povtoramy(port, zapyt, taimaut, sprob):
    """Повтор із експоненційною витримкою: 0.2 · 0.4 · 0.8 ..."""
    ostannya = None
    for sproba in range(sprob):
        try:
            return poslaty(port, zapyt, taimaut), sproba + 1
        except (OSError, ConnectionError, json.JSONDecodeError) as e:
            ostannya = e
            if sproba + 1 < sprob:
                time.sleep(0.2 * 2 ** sproba)
    raise ostannya


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=50007,
                   help="50007 — напряму до служби, 50010 — через ненадійну мережу")
    p.add_argument("--kilkist", type=int, default=10, help="скільки замірів надіслати")
    p.add_argument("--taimaut", type=float, default=None,
                   help="секунд на спробу; без нього клієнт чекає скільки завгодно")
    p.add_argument("--sprob", type=int, default=1, help="скільки разів пробувати кожен запис")
    p.add_argument("--kliuch", action="store_true",
                   help="додавати ключ ідемпотентності — служба не порахує повтор двічі")
    args = p.parse_args()

    print(f"[клієнт] порт {args.port} · таймаут {args.taimaut} · спроб {args.sprob}"
          f" · ключ {'так' if args.kliuch else 'ні'}")
    nadislano = 0
    pomylok = 0
    povtoriv = 0
    t_start = time.perf_counter()

    for i in range(args.kilkist):
        zapys = {"rozmir": "1200x800", "chas": round(0.15 + i * 0.01, 3)}
        zapyt = {"dia": "dodaty", "zapys": zapys}
        if args.kliuch:
            zapyt["kliuch"] = str(uuid.uuid4())
        t0 = time.perf_counter()
        try:
            vidpovid, sprob = poslaty_z_povtoramy(args.port, zapyt, args.taimaut, args.sprob)
            povtoriv += sprob - 1
            nadislano += 1
            print(f"  {i + 1:>3}. {vidpovid} · {1000 * (time.perf_counter() - t0):.0f} мс"
                  + (f" · спроб {sprob}" if sprob > 1 else ""))
        except Exception as e:                                      # noqa: BLE001
            pomylok += 1
            print(f"  {i + 1:>3}. ❌ {type(e).__name__}: {e}"
                  f" · {1000 * (time.perf_counter() - t0):.0f} мс")

    zagalom = time.perf_counter() - t_start
    print(f"\n[клієнт] надіслано успішно {nadislano} з {args.kilkist}"
          f" · помилок {pomylok} · зайвих спроб {povtoriv} · разом {zagalom:.2f} с")

    # головне питання теми: а скільки служба нарахувала насправді?
    try:
        stan = poslaty(args.port if args.port == 50007 else 50007, {"dia": "stan"}, 5)
        print(f"[служба] у журналі записів: {stan['vsogo']}"
              f" · унікальних ключів: {stan['unikalnyh_kliuchiv']}")
        if stan["vsogo"] > args.kilkist:
            print(f"⚠️  ДУБЛІКАТИ: служба записала {stan['vsogo']} замість {args.kilkist} —"
                  f" повтори порахувались як нові записи ({stan['vsogo'] - args.kilkist} зайвих)")
        elif stan["vsogo"] > nadislano:
            print(f"⚠️  НЕВИЗНАЧЕНІСТЬ: служба прийняла {stan['vsogo']}, а клієнт упевнений"
                  f" лише в {nadislano}. Загубились ВІДПОВІДІ, а не дані —"
                  f" клієнт просто не знає, що сталось")
        elif stan["vsogo"] < args.kilkist:
            print(f"⚠️  ВТРАТИ: {args.kilkist - stan['vsogo']} записів не дійшли")
        else:
            print("✔ рівно стільки, скільки надсилали")
    except OSError as e:
        print("[клієнт] стан служби не дізнатись:", e)


if __name__ == "__main__":
    main()
