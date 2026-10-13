"""Спостерігач: підписується на тему брокера й друкує все, що туди публікують.

    python sposterigach.py --imya S1
    python sposterigach.py --imya S2 --tema postup

Спостерігач нічого не забирає з черг — він лише слухає. Двоє спостерігачів
отримують **кожне** повідомлення обоє. Зупинити — Ctrl+C.
"""

import argparse
import select
import sys

from ramka import nadislaty, otrymaty, pidkliuchytys


def main():
    sys.stdout.reconfigure(line_buffering=True)   # рядки видно одразу, навіть у перенаправленому виводі
    p = argparse.ArgumentParser()
    p.add_argument("--imya", default="S1")
    p.add_argument("--port", type=int, default=50030, help="порт брокера")
    p.add_argument("--tema", default="postup")
    args = p.parse_args()

    sock = pidkliuchytys(args.port)
    nadislaty(sock, {"dia": "pidpysatys", "tema": args.tema})
    print(f"[{args.imya}] слухаю тему «{args.tema}»…")
    otrymano = 0
    try:
        while True:
            # чекаємо не довше секунди, щоб Ctrl+C на Windows спрацьовував одразу
            if not select.select([sock], [], [], 1.0)[0]:
                continue
            m = otrymaty(sock)
            otrymano += 1
            d = m["dani"]
            if isinstance(d, dict) and "gotovo" in d:
                smuga = "█" * round(20 * d["gotovo"] / d["vsogo"])
                print(f"[{args.imya}] {d['zapusk']} {smuga:<20} {d['gotovo']}/{d['vsogo']} · від {d['vid']}")
            else:
                print(f"[{args.imya}] {m}")
    except KeyboardInterrupt:
        pass
    except (ConnectionError, OSError, ValueError) as e:
        print(f"[{args.imya}] {type(e).__name__}: {e}")
    finally:
        print(f"[{args.imya}] отримано повідомлень: {otrymano}")
        sock.close()


if __name__ == "__main__":
    main()
