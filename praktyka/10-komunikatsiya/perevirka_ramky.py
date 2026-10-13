"""Перевірка вашої `otrymaty` з `ramka.py` — п'ять ситуацій, які трапляються в мережі.

    python perevirka_ramky.py

Жодної мережі не треба: два кінці одного з'єднання створюються в цьому ж процесі.
Кожна перевірка має обмеження 3 с, тож «зависла» теж буде видно.
"""

import importlib
import json
import socket
import struct
import sys
import threading
import time

if len(sys.argv) > 1 and sys.argv[1].endswith(".py"):        # інший файл: шлях до .py
    import importlib.util
    _spec = importlib.util.spec_from_file_location("ramka_insha", sys.argv[1])
    ramka = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ramka)
else:
    ramka = importlib.import_module("ramka")


def para():
    a, b = socket.socketpair()
    b.settimeout(3)
    return a, b


def ramka_bajty(obj):
    dani = json.dumps(obj, ensure_ascii=False).encode()
    return struct.pack(">I", len(dani)) + dani


def u_fon(f):
    t = threading.Thread(target=f, daemon=True)
    t.start()
    return t


def t1_male():
    a, b = para()
    m = {"dia": "stan"}
    ramka.nadislaty(a, m)
    return ramka.otrymaty(b) == m


def t2_velyke():
    a, b = para()
    m = {"y0": 0, "ryadky": [[300] * 1200 for _ in range(50)]}   # ~ як 50 рядків Мандельброта
    u_fon(lambda: ramka.nadislaty(a, m))
    return ramka.otrymaty(b) == m


def t3_dva_razom():
    a, b = para()
    m1, m2 = {"n": 1, "tekst": "перше"}, {"n": 2, "tekst": "друге"}
    a.sendall(ramka_bajty(m1) + ramka_bajty(m2))           # одним шматком
    return ramka.otrymaty(b) == m1 and ramka.otrymaty(b) == m2


def t4_po_shmatochku():
    a, b = para()
    m = {"tekst": "повідомлення, яке їде по сім байтів"}
    bajty = ramka_bajty(m)

    def slaty():
        for i in range(0, len(bajty), 7):
            a.sendall(bajty[i:i + 7])
            time.sleep(0.01)
    u_fon(slaty)
    return ramka.otrymaty(b) == m


def t5_obryv():
    a, b = para()
    a.sendall(struct.pack(">I", 1000) + b'{"poch')            # обіцяли 1000 байтів, дали 10
    a.close()
    try:
        ramka.otrymaty(b)
    except ConnectionError:
        return True
    return False


TESTY = [
    (t1_male, "мале повідомлення", "це має працювати навіть у наївній версії"),
    (t2_velyke, "велике повідомлення ~240 КБ",
     "recv повертає стільки, скільки прийшло, а не скільки треба: читайте в циклі, доки не наберете довжину"),
    (t3_dva_razom, "два повідомлення одним шматком",
     "TCP — потік байтів: прочитали зайве — воно належить наступному повідомленню; читайте рівно довжину"),
    (t4_po_shmatochku, "повідомлення приходить по 7 байтів",
     "навіть 4 байти довжини можуть прийти частинами"),
    (t5_obryv, "з'єднання обірвалось посеред повідомлення",
     "recv повернув b'' — це кінець з'єднання; підніміть ConnectionError, а не повертайте сміття"),
]


def main():
    print(f"перевіряю {ramka.__file__}\n")
    proishlo = 0
    for test, nazva, pidkazka in TESTY:
        try:
            ok = test()
            prychyna = "" if ok else "повернула не те, що надсилали"
        except socket.timeout:
            ok, prychyna = False, "зависла: чекала байтів, яких ніхто не надішле"
        except Exception as e:                       # noqa: BLE001 — показати будь-що
            ok, prychyna = False, f"{type(e).__name__}: {str(e)[:70]}"
        proishlo += ok
        print(f"  {'✔' if ok else '❌'} {nazva}")
        if not ok:
            print(f"      {prychyna}")
            print(f"      підказка: {pidkazka}")
    print(f"\nпройдено {proishlo} з {len(TESTY)}")
    if proishlo == len(TESTY):
        print("✔ рамка правильна — можна переходити до кроку 2")


if __name__ == "__main__":
    main()
