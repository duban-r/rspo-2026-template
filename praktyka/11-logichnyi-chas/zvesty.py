"""Звести журнали трьох вузлів в одну історію — двома способами — і перевірити причинність.

    python zvesty.py                 # дві таблиці: за фізичним часом і за логічним
    python zvesty.py --para A2 C1    # ці дві події — причина й наслідок чи конкурентні?

«Причинність» тут не вгадується: скрипт знає, яке повідомлення яке отримання спричинило,
і будує ланцюжки «сталося раніше» за трьома правилами теми.
"""

import argparse
import glob
import json
import sys


def zavantazhyty():
    podii = []
    for f in sorted(glob.glob("zhurnal-*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            podii += [json.loads(r) for r in fh if r.strip()]
    if not podii:
        sys.exit("журналів zhurnal-*.jsonl немає — спершу запустіть три вузли (крок 2)")
    return podii


def hrafa(podii):
    """Ребра «сталося раніше»: сусідні події одного вузла + надіслано → отримано."""
    za_id = {p["id"]: p for p in podii}
    nastupni = {p["id"]: [] for p in podii}
    po_vuzlah = {}
    for p in podii:
        po_vuzlah.setdefault(p["vuzol"], []).append(p)
    for spysok in po_vuzlah.values():
        spysok.sort(key=lambda p: int(p["id"][1:]))
        for a, b in zip(spysok, spysok[1:]):
            nastupni[a["id"]].append(b["id"])
    povidomlennia = []
    for p in podii:
        if p.get("prychyna") in za_id:
            nastupni[p["prychyna"]].append(p["id"])
            povidomlennia.append((za_id[p["prychyna"]], p))
    return za_id, nastupni, povidomlennia


def shliakh(nastupni, a, b):
    """Ланцюжок a → … → b або None."""
    stos, bachyly = [[a]], {a}
    while stos:
        sh = stos.pop()
        if sh[-1] == b:
            return sh
        for n in nastupni[sh[-1]]:
            if n not in bachyly:
                bachyly.add(n)
                stos.append(sh + [n])
    return None


def tablytsia(podii, kliuch, nazva, povidomlennia):
    poriadok = sorted(podii, key=kliuch)
    mistse = {p["id"]: i for i, p in enumerate(poriadok)}
    t0 = min(p["fiz"] for p in podii)
    zlami = {o["id"] for n, o in povidomlennia if mistse[n["id"]] > mistse[o["id"]]}
    print(f"\n{nazva}")
    print(f"{'#':>3}  {'фіз., мс':>9}  {'L':>3}  {'id':<4} подія")
    for i, p in enumerate(poriadok, 1):
        mitka = "  ⚠️ отримано РАНІШЕ, ніж надіслано" if p["id"] in zlami else ""
        tekst = {"vlasna": "• ", "nadislano": "→ ", "otrymano": "← "}[p["vyd"]] + p["tekst"]
        print(f"{i:>3}  {1000 * (p['fiz'] - t0):9.1f}  {p['L']:>3}  {p['id']:<4} {tekst}{mitka}")
    print(f"порушень причинності (отримання стоїть раніше за своє надсилання): {len(zlami)}")
    return len(zlami)


def main():
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--para", nargs=2, metavar=("X", "Y"), help="перевірити дві події")
    args = ap.parse_args()

    podii = zavantazhyty()
    za_id, nastupni, povidomlennia = hrafa(podii)

    if args.para:
        x, y = args.para
        for i in (x, y):
            if i not in za_id:
                sys.exit(f"події {i} немає в журналах")
        sh = shliakh(nastupni, x, y) or shliakh(nastupni, y, x)
        print(f"{x}: L={za_id[x]['L']} · {za_id[x]['tekst']}")
        print(f"{y}: L={za_id[y]['L']} · {za_id[y]['tekst']}")
        if sh:
            print("ПРИЧИНА → НАСЛІДОК: " + " → ".join(sh))
        else:
            print("КОНКУРЕНТНІ: жодного ланцюжка «сталося раніше» ні в той, ні в інший бік.")
            if za_id[x]["L"] != za_id[y]["L"]:
                print("   Зверніть увагу: L у них різні — і це нічого не означає.")
        return

    tablytsia(podii, lambda p: p["fiz"], "ЗА ФІЗИЧНИМ ЧАСОМ (годинники вузлів)", povidomlennia)
    if all(p["L"] == 0 for p in podii):
        print("\nЗА ЛОГІЧНИМ ЧАСОМ: усі L = 0 — годинник Лемпорта ще не написаний (крок 1).")
        return
    tablytsia(podii, lambda p: (p["L"], p["vuzol"]), "ЗА ЛОГІЧНИМ ЧАСОМ (L, потім ім'я вузла)",
              povidomlennia)

    pary = [(a, b) for a in za_id for b in za_id if a != b and shliakh(nastupni, a, b)]
    zly = [(a, b) for a, b in pary if not za_id[a]["L"] < za_id[b]["L"]]
    print(f"\nпричинних пар: {len(pary)} · з них L(причина) < L(наслідок): {len(pary) - len(zly)}"
          + ("  ✔ властивість Лемпорта виконується" if not zly else f"  ❌ порушено, напр. {zly[0]}"))

    V = {p["id"]: p["V"] for p in podii}
    if any(any(v.values()) for v in V.values()):
        def menshe(u, w):
            return all(u[k] <= w[k] for k in u) and u != w
        ids = sorted(za_id)
        konk_v = {(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]
                  if not menshe(V[a], V[b]) and not menshe(V[b], V[a])}
        konk_ist = {(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]
                    if not shliakh(nastupni, a, b) and not shliakh(nastupni, b, a)}
        print(f"векторний годинник: конкурентних пар {len(konk_v)} · насправді {len(konk_ist)} · "
              + ("✔ збіг" if konk_v == konk_ist else "❌ не збігається"))


if __name__ == "__main__":
    main()
