"""
РСПО, практична 5. Знайти й полагодити.

ЩО ЦЕ

  Модель складу. Кілька процесів паралельно обробляють замовлення
  й списують товар із залишку. Наприкінці програма сама перевіряє
  два інваріанти:

    1. Залишок ніколи не стає від'ємним.
    2. Відвантажено + залишок = початковий запас.

  Обидва мають виконуватись завжди. Вони не виконуються.

ЩО ЗРОБИТИ

  1. Запустити кілька разів як є. Записати числа в `zamiry.md`.
  2. Знайти місця, де інваріанти ламаються. Їх БІЛЬШЕ ОДНОГО.
  3. Полагодити, не втративши паралельність:
     ⚠️ загорнути всю функцію в один замок — це не розв'язання,
     а вимкнення паралельності. Захищати треба мінімальну ділянку.
  4. Довести, що полагоджено: 10 прогонів поспіль без порушень.
  5. Пояснити в звіті, ЧОМУ саме там ламалось.

⚠️ ПРО ВІДТВОРЮВАНІСТЬ

  Тут навмисно ПРОЦЕСИ, а не потоки. З потоками помилка на швидкій
  машині може не проявитись жодного разу, і ви зробите хибний
  висновок, що все гаразд. З процесами й спільною пам'яттю вона
  проявляється на будь-якому обладнанні.

  Це саме по собі — тема для абзацу у звіті.

ЗАПУСК:  python zlamane.py
"""

import multiprocessing as mp
import os
import platform
import random
import sys
import time

ZAPAS_POCHATKOVYI = 30_000
PROTSESIV = 4
ZAMOVLEN_NA_PROTSES = 20_000
MAX_U_ZAMOVLENNI = 3


def obrobyty_zamovlennya(zalyshok, vidvantazheno, vidmov, nasinnya):
    """Один робітник складу. Обробляє свою пачку замовлень."""
    rnd = random.Random(nasinnya)

    for _ in range(ZAMOVLEN_NA_PROTSES):
        kilkist = rnd.randint(1, MAX_U_ZAMOVLENNI)

        # перевіряємо, чи вистачає товару
        if zalyshok.value >= kilkist:
            # списуємо
            zalyshok.value = zalyshok.value - kilkist
            # рахуємо, скільки відвантажили
            vidvantazheno.value = vidvantazheno.value + kilkist
        else:
            vidmov.value = vidmov.value + 1


def pasport():
    print("=" * 68)
    print("УМОВИ ЗАПУСКУ")
    print("=" * 68)
    print("  Python        :", sys.version.split()[0])
    print("  процесор      :", platform.processor())
    print("  логічних ядер :", os.cpu_count())
    print("  ОС            :", platform.platform())
    print("  навантаження  : %d процесів x %d замовлень"
          % (PROTSESIV, ZAMOVLEN_NA_PROTSES))
    print()


def prognaty(nomer):
    zalyshok = mp.Value("i", ZAPAS_POCHATKOVYI)
    vidvantazheno = mp.Value("i", 0)
    vidmov = mp.Value("i", 0)

    procesy = [
        mp.Process(target=obrobyty_zamovlennya,
                   args=(zalyshok, vidvantazheno, vidmov, 1000 + i))
        for i in range(PROTSESIV)
    ]

    t0 = time.perf_counter()
    for p in procesy:
        p.start()
    for p in procesy:
        p.join()
    tryvalist = time.perf_counter() - t0

    z = zalyshok.value
    v = vidvantazheno.value
    vm = vidmov.value

    # ── перевірка інваріантів ──────────────────────────────────
    porushennya = []
    if z < 0:
        porushennya.append("залишок від'ємний: %d" % z)
    if v + z != ZAPAS_POCHATKOVYI:
        porushennya.append("баланс не сходиться: %d + %d = %d, а має бути %d"
                           % (v, z, v + z, ZAPAS_POCHATKOVYI))

    stan = "OK" if not porushennya else "ПОРУШЕНО"
    print("  прогін %d:  залишок %8d   відвантажено %8d   відмов %6d   "
          "%6.2f c   %s" % (nomer, z, v, vm, tryvalist, stan))
    for p in porushennya:
        print("             -> " + p)

    return not porushennya


if __name__ == "__main__":
    pasport()
    print("=" * 68)
    print("ПРОГОНИ.  Початковий запас:", ZAPAS_POCHATKOVYI)
    print("=" * 68)

    chysto = 0
    PROGONIV = 5
    for i in range(1, PROGONIV + 1):
        if prognaty(i):
            chysto += 1

    print()
    print("=" * 68)
    print("  Без порушень: %d із %d" % (chysto, PROGONIV))
    print("=" * 68)
    if chysto < PROGONIV:
        print("  Помилка проявилась. Знайдіть її й поясніть.")
        print("  Підказка, з чого почати: скільки окремих дій ховається")
        print("  за рядком `x.value = x.value + 1`?")
    else:
        print("  Порушень не виявлено — але це НЕ означає, що їх немає.")
        print("  Збільште ZAMOVLEN_NA_PROTSES або PROTSESIV і повторіть.")
        print("  Помилка, яку не видно, лишається помилкою.")
