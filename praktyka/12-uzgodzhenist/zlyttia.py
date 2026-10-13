"""Як репліка зливає свою версію з чужою. Крок 4 — ваш.

Версія — це dict:
    {"znach": <значення>, "ts": <час запису за годинником репліки>, "vuzol": "R1"}
Для журналу замірів `znach` — список записів {"id": "a1b2c3", "tekst": "...", "vuzol": "R1"}.

Перевірка: `python perevirka_zlyttia.py`.
"""


def obyednaty(mia, chuzha):
    """останній запис виграє (LWW) — за часом репліки, при рівності — за іменем

    mia — версія цієї репліки (або None, якщо ключа ще немає), chuzha — версія сусіда.
    Повертає версію, яка лишиться на репліці.
    """
    if mia is None:
        return chuzha
    if chuzha is None:
        return mia
    return max(mia, chuzha, key=lambda v: (v["ts"], v["vuzol"]))
