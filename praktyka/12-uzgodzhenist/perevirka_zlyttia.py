"""Перевірка `obyednaty` з `zlyttia.py`: чи не губить вона записи журналу.

    python perevirka_zlyttia.py
"""

import importlib.util
import sys

shliakh = sys.argv[1] if len(sys.argv) > 1 else "zlyttia.py"
_spec = importlib.util.spec_from_file_location("zlyttia_pid_perevirkoiu", shliakh)
z = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(z)


def zapys(i, tekst, vuzol):
    return {"id": i, "tekst": tekst, "vuzol": vuzol}


def versiya(spysok, ts, vuzol):
    return {"znach": spysok, "ts": ts, "vuzol": vuzol}


def idy(v):
    return sorted(e["id"] for e in v["znach"])


spilne = zapys("a1", "спільний запис", "R1")
liva = versiya([spilne, zapys("b2", "з лівого боку розриву", "R1")], 100.0, "R1")
prava = versiya([spilne, zapys("c3", "з правого боку", "R3")], 100.4, "R3")

TESTY = [
    ("ключа ще не було — береться чужа версія",
     lambda: z.obyednaty(None, liva) == liva, "None означає «у мене нічого немає»"),
    ("записи з обох боків розриву лишаються обидва",
     lambda: idy(z.obyednaty(liva, prava)) == ["a1", "b2", "c3"],
     "об'єднуйте списки, а не обирайте один із двох; спільний запис упізнавайте за id"),
    ("порядок аргументів не важить (R1 зливає з R3 так само, як R3 з R1)",
     lambda: idy(z.obyednaty(liva, prava)) == idy(z.obyednaty(prava, liva)),
     "результат не має залежати від того, чия версія «моя»"),
    ("злиття з собою нічого не дублює",
     lambda: idy(z.obyednaty(liva, liva)) == ["a1", "b2"], "той самий id — той самий запис"),
    ("повторне злиття не змінює результату",
     lambda: idy(z.obyednaty(z.obyednaty(liva, prava), prava)) == ["a1", "b2", "c3"],
     "реплікація може прийти двічі — злиття має бути ідемпотентним"),
    ("звичайні значення (не списки) — як і раніше, новіший виграє",
     lambda: z.obyednaty(versiya("старе", 1.0, "R1"), versiya("нове", 2.0, "R2"))["znach"] == "нове",
     "для не-списків лишіть правило «останній виграє»"),
]


def main():
    print(f"перевіряю {shliakh}\n")
    ok = 0
    for nazva, f, pidkazka in TESTY:
        try:
            prav = bool(f())
        except Exception as e:                       # noqa: BLE001
            prav = False
            pidkazka = f"{type(e).__name__}: {e} · {pidkazka}"
        ok += prav
        print(f"  {'✔' if prav else '❌'} {nazva}")
        if not prav:
            print(f"      підказка: {pidkazka}")
    print(f"\nпройдено {ok} з {len(TESTY)}")
    if ok == len(TESTY):
        print("✔ злиття не губить записів — перезапустіть репліки й повторіть розрив")


if __name__ == "__main__":
    main()
