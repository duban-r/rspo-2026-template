"""Перевірка `godynnyk.py` — правила Лемпорта (і векторного годинника, якщо ви його вже написали).

    python perevirka_godynnyka.py
"""

import importlib.util
import sys

shliakh = sys.argv[1] if len(sys.argv) > 1 else "godynnyk.py"
_spec = importlib.util.spec_from_file_location("godynnyk_pid_perevirkoiu", shliakh)
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)


def lamport():
    rez = []
    a = g.Lamport()
    rez.append(("власна подія збільшує годинник: 1, 2",
                [a.vlasna_podiya(), a.vlasna_podiya()] == [1, 2],
                "правило 1: перед кожною власною подією L = L + 1"))
    a = g.Lamport()
    rez.append(("відправлення — теж подія: 1",
                a.pered_nadsylanniam() == 1,
                "надсилання — подія цього вузла, тож спершу L = L + 1, і саме це L іде в повідомлення"))
    a = g.Lamport()
    a.vlasna_podiya()
    rez.append(("отримали більше число (Lm = 7, у нас 1): стає 8",
                a.pislia_otrymannia(7) == 8,
                "правило 3: L = max(L, Lm) + 1"))
    a = g.Lamport()
    for _ in range(5):
        a.vlasna_podiya()
    rez.append(("отримали менше число (Lm = 2, у нас 5): стає 6, а не 3",
                a.pislia_otrymannia(2) == 6,
                "max — бо годинник ніколи не йде назад"))
    # причинність: подія-причина завжди менша за наслідок
    x, y = g.Lamport(), g.Lamport()
    for _ in range(3):
        y.vlasna_podiya()
    Lx = x.pered_nadsylanniam()
    Ly = y.pislia_otrymannia(Lx)
    rez.append(("причина менша за наслідок на іншому вузлі",
                Lx < Ly, "отримання має бути більшим і за своє L, і за Lm"))
    return rez


def vektor():
    imena = ["A", "B", "C"]
    a, b = g.Vektornyi(imena, "A"), g.Vektornyi(imena, "B")
    if a.vlasna_podiya() == {"A": 0, "B": 0, "C": 0}:
        return None                                   # ще не писали — не лаємо
    a, b = g.Vektornyi(imena, "A"), g.Vektornyi(imena, "B")
    rez = []
    rez.append(("вектор: власна подія A", a.vlasna_podiya() == {"A": 1, "B": 0, "C": 0},
                "збільшуйте лише СВІЙ елемент"))
    vm = a.pered_nadsylanniam()
    b.vlasna_podiya()
    rez.append(("вектор: B отримав від A", b.pislia_otrymannia(vm) == {"A": 2, "B": 2, "C": 0},
                "поелементний максимум, потім +1 до свого елемента"))
    return rez


def main():
    print(f"перевіряю {shliakh}\n")
    vsi = lamport()
    v = vektor()
    if v is None:
        print("  (векторний годинник ще не написаний — це ⭐1, пропускаю)\n")
    else:
        vsi += v
    ok = 0
    for nazva, prav, pidkazka in vsi:
        print(f"  {'✔' if prav else '❌'} {nazva}")
        if not prav:
            print(f"      підказка: {pidkazka}")
        ok += prav
    print(f"\nпройдено {ok} з {len(vsi)}")
    if ok == len(vsi):
        print("✔ годинник правильний — можна запускати вузли")


if __name__ == "__main__":
    main()
