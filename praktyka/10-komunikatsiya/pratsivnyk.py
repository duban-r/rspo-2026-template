"""Працівник: бере завдання з черги брокера, рахує рядки, кладе результат у чергу.

    python pratsivnyk.py --imya P1
    python pratsivnyk.py --imya P2 --povilno 3     # утричі повільніша машина
    python pratsivnyk.py --imya P3 --pomerty-pislia 5   # ⭐2: помре після 5-го результату, не підтвердивши

Запускайте скільки завгодно копій у різних терміналах — кожна стане окремим
«вузлом». Між собою вони не знають одне про одного: усе йде через брокер.
Зупинити — Ctrl+C.
"""

import argparse
import os
import sys
import time

from mandelbrot import ryadok
from ramka import pidkliuchytys, zapyt


def main():
    sys.stdout.reconfigure(line_buffering=True)   # рядки видно одразу, навіть у перенаправленому виводі
    p = argparse.ArgumentParser()
    p.add_argument("--imya", default=os.environ.get("HOSTNAME", "P1")[:12],
                   help="ім'я працівника — видно в результатах (у контейнері — ім'я контейнера)")
    p.add_argument("--port", type=int, default=50030, help="порт брокера")
    p.add_argument("--povilno", type=float, default=1.0,
                   help="у скільки разів ця «машина» повільніша (імітація слабкого вузла)")
    p.add_argument("--pomerty-pislia", type=int, default=0,
                   help="⭐2: впасти одразу після N-го результату, ще до підтвердження")
    args = p.parse_args()

    sock = pidkliuchytys(args.port)
    print(f"[{args.imya}] під'єднався до брокера :{args.port}, чекаю завдань…")
    zrobleno = ryadkiv = 0
    try:
        while True:
            v = zapyt(sock, {"dia": "vzyaty", "cherga": "zavdannya", "chekaty": 1})
            if not v.get("ok"):
                continue                                  # черга порожня — чекаємо далі
            z = v["dani"]
            t0 = time.perf_counter()
            ryadky = [ryadok(y) for y in range(z["y0"], z["y1"])]
            if args.povilno > 1:
                time.sleep((args.povilno - 1) * (time.perf_counter() - t0))
            zapyt(sock, {"dia": "poklasty", "cherga": "rezultaty",
                         "dani": {"zapusk": z["zapusk"], "y0": z["y0"],
                                  "ryadky": ryadky, "pratsivnyk": args.imya}})
            if args.pomerty_pislia and zrobleno + 1 == args.pomerty_pislia:
                print(f"[{args.imya}] результат {zrobleno + 1} надіслано — і падаю, не підтвердивши")
                os._exit(1)                               # як вимкнене світло: без прибирання
            if v.get("treba_pidtverdyty"):
                zapyt(sock, {"dia": "pidtverdyty", "id": v["id"]})
            zrobleno += 1
            ryadkiv += len(ryadky)
            if zrobleno % 20 == 0:
                print(f"[{args.imya}] завдань {zrobleno} · рядків {ryadkiv}")
    except KeyboardInterrupt:
        pass
    except (ConnectionError, OSError) as e:
        print(f"[{args.imya}] брокер недоступний: {type(e).__name__}: {e}")
    finally:
        print(f"[{args.imya}] зупинено · завдань {zrobleno} · рядків {ryadkiv}")
        sock.close()


if __name__ == "__main__":
    main()
