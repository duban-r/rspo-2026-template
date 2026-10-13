"""Логічні годинники. Ваш крок 1 — `Lamport`; ⭐1 — `Vektornyi`.

`vuzol.py` викликає ці методи на кожну подію:

    L = g.vlasna_podiya()          # щось сталося всередині вузла
    L = g.pered_nadsylanniam()     # число, яке піде разом із повідомленням
    L = g.pislia_otrymannia(Lm)    # прийшло повідомлення з числом Lm

Кожен метод повертає значення годинника для ЦІЄЇ події.
Перевірка: `python perevirka_godynnyka.py`.
"""


class Lamport:
    def __init__(self):
        self.L = 0

    def vlasna_podiya(self):
        # TODO крок 1: правило 1
        return self.L

    def pered_nadsylanniam(self):
        # TODO крок 1: відправлення — теж подія
        return self.L

    def pislia_otrymannia(self, Lm):
        # TODO крок 1: правило 3
        return self.L


class Vektornyi:
    """⭐1. Вектор: скільки подій кожного вузла «відомо» цьому вузлу.

    imena — усі вузли системи, наприклад ["A", "B", "C"]; ja — ім'я цього вузла.
    Методи повертають КОПІЮ вектора як dict {"A": 2, "B": 0, "C": 1}.
    """

    def __init__(self, imena, ja):
        self.ja = ja
        self.V = {i: 0 for i in imena}

    def vlasna_podiya(self):
        # TODO ⭐1
        return dict(self.V)

    def pered_nadsylanniam(self):
        # TODO ⭐1
        return dict(self.V)

    def pislia_otrymannia(self, Vm):
        # TODO ⭐1
        return dict(self.V)
