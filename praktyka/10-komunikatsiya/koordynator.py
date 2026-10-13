"""Координатор: ріже зображення на завдання, роздає через брокер, збирає результат.

    python koordynator.py --poslidovno        # еталон: час і контрольна сума → etalon.json
    python koordynator.py --shmatok 10        # через брокер, по 10 рядків у завданні

Що друкує наприкінці: час, прискорення відносно еталона, чи збігся результат,
скільки завдань зробив кожен працівник, скільки дій пройшло через брокер,
скільки рядків прийшло двічі і яких бракує.

Під час роботи публікує прогрес у тему «postup» — його бачать `sposterigach.py`.
"""

import argparse
import hashlib
import json
import os
import platform
import sys
import time
import uuid

import mandelbrot
from ramka import pidkliuchytys, zapyt

ETALON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etalon.json")


def kontrolna_suma(ryadky):
    return hashlib.sha256(json.dumps(ryadky).encode()).hexdigest()[:16]


def poslidovno():
    print(f"еталон: {mandelbrot.W}×{mandelbrot.H}, max_iter={mandelbrot.MAX_ITER}, "
          f"процесор: {platform.processor() or platform.machine()}, ядер {os.cpu_count()}")
    t0 = time.perf_counter()
    ryadky = [mandelbrot.ryadok(y) for y in range(mandelbrot.H)]
    chas = time.perf_counter() - t0
    suma = kontrolna_suma(ryadky)
    with open(ETALON, "w", encoding="utf-8") as f:
        json.dump({"chas": round(chas, 3), "suma": suma, "W": mandelbrot.W,
                   "H": mandelbrot.H, "MAX_ITER": mandelbrot.MAX_ITER}, f)
    print(f"послідовно: {chas:.2f} с · контрольна сума {suma} → etalon.json")


def rozislaty(sock, zapusk, H, k):
    """Покласти в чергу всі завдання по k рядків. Синхронно: на кожне — чекаємо «ok»."""
    zavdan = 0
    for y0 in range(0, H, k):
        zapyt(sock, {"dia": "poklasty", "cherga": "zavdannya",
                     "dani": {"zapusk": zapusk, "y0": y0, "y1": min(y0 + k, H)}})
        zavdan += 1
    return zavdan


def zibraty(sock, args, zapusk, ryadky, stat):
    """Забирати результати, доки не зберемо всі рядки або не вийде таймаут."""
    H = len(ryadky)
    opublikovano_krokiv = 0                    # прогрес — кожні 5 %, тобто 20 повідомлень
    ostannii = time.monotonic()
    while stat["gotovo"] < H:
        v = zapyt(sock, {"dia": "vzyaty", "cherga": "rezultaty", "chekaty": 1})
        if not v.get("ok"):
            if time.monotonic() - ostannii > args.taimaut:
                print(f"[координатор] {args.taimaut:g} с жодного результату — припиняю чекати")
                break
            continue
        if v.get("treba_pidtverdyty"):
            zapyt(sock, {"dia": "pidtverdyty", "id": v["id"]})
        r = v["dani"]
        if r.get("zapusk") != zapusk:
            stat["chuzhykh"] += 1
            continue
        ostannii = time.monotonic()
        if ryadky[r["y0"]] is not None:
            stat["dublikativ"] += 1
            continue
        for i, rd in enumerate(r["ryadky"]):
            ryadky[r["y0"] + i] = rd
        stat["gotovo"] += len(r["ryadky"])
        stat["hto"][r["pratsivnyk"]] = stat["hto"].get(r["pratsivnyk"], 0) + 1
        if not args.bez_postupu and stat["gotovo"] * 20 // H > opublikovano_krokiv:
            zapyt(sock, {"dia": "opublikuvaty", "tema": "postup",
                         "dani": {"zapusk": zapusk, "gotovo": stat["gotovo"], "vsogo": H,
                                  "vid": r["pratsivnyk"]}})
            opublikovano_krokiv = stat["gotovo"] * 20 // H


def cherez_broker(args):
    etalon = None
    if os.path.exists(ETALON):
        with open(ETALON, encoding="utf-8") as f:
            etalon = json.load(f)
    else:
        print("⚠️  etalon.json немає — спершу `python koordynator.py --poslidovno`; "
              "без нього не буде ні прискорення, ні перевірки результату")

    H, k = mandelbrot.H, args.shmatok
    zapusk = uuid.uuid4().hex[:8]
    sock = pidkliuchytys(args.port)
    for q in ("zavdannya", "rezultaty"):
        zapyt(sock, {"dia": "ochystyty", "cherga": q})
    st0 = zapyt(sock, {"dia": "stan"})["lichylnyky"]

    t0 = time.perf_counter()
    zavdan = rozislaty(sock, zapusk, H, k)
    t_rozsylka = time.perf_counter() - t0
    print(f"[координатор] запуск {zapusk} · завдань {zavdan} по {k} рядк. · "
          f"розіслано за {t_rozsylka:.2f} с")

    ryadky = [None] * H
    stat = {"gotovo": 0, "dublikativ": 0, "chuzhykh": 0, "hto": {}}
    povidomlen = None
    try:
        zibraty(sock, args, zapusk, ryadky, stat)
        st1 = zapyt(sock, {"dia": "stan"})["lichylnyky"]
        povidomlen = sum(st1.values()) - sum(st0.values())
    except (ConnectionError, OSError) as e:
        print(f"[координатор] брокер недоступний ({type(e).__name__}) — далі нічого не прийде")
    chas = time.perf_counter() - t0
    sock.close()

    brakuie = [y for y in range(H) if ryadky[y] is None]
    print()
    print(f"час через брокер: {chas:.2f} с  (з них розсилка завдань {t_rozsylka:.2f} с)")
    if etalon and not brakuie:
        print(f"послідовно (еталон): {etalon['chas']:.2f} с · прискорення ×{etalon['chas'] / chas:.2f}")
    print("обслужили: " + (" · ".join(f"{p}: {n}" for p, n in sorted(stat["hto"].items())) or "—"))
    print(f"дій через брокер: {povidomlen if povidomlen is not None else '?'} · "
          f"дублікатів: {stat['dublikativ']}"
          + (f" · чужих (з минулого запуску): {stat['chuzhykh']}" if stat["chuzhykh"] else ""))
    if brakuie:
        print(f"❌ бракує рядків: {len(brakuie)} (перші: {brakuie[:8]})")
    elif etalon and kontrolna_suma(ryadky) == etalon["suma"]:
        print("✔ результат збігається з послідовним")
    elif etalon:
        print("❌ результат НЕ збігається з послідовним")
    print(f"\nрядок для чату: · {len(stat['hto'])} прац. · шматок {k} · {chas:.2f} с"
          + (f" · ×{etalon['chas'] / chas:.2f}" if etalon and not brakuie else "")
          + (f" · бракує {len(brakuie)}" if brakuie else " · ✔"))


def main():
    sys.stdout.reconfigure(line_buffering=True)   # рядки видно одразу, навіть у перенаправленому виводі
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=50030, help="порт брокера")
    p.add_argument("--poslidovno", action="store_true",
                   help="порахувати локально без брокера й записати еталон")
    p.add_argument("--shmatok", type=int, default=10, help="рядків в одному завданні")
    p.add_argument("--taimaut", type=float, default=10,
                   help="скільки секунд чекати без жодного нового результату")
    p.add_argument("--bez-postupu", action="store_true", help="не публікувати прогрес")
    args = p.parse_args()
    if args.poslidovno:
        poslidovno()
    else:
        cherez_broker(args)


if __name__ == "__main__":
    main()
