# Практична 06. NumPy та Numba

Тема 6 · до **8 балів** · практика — друга пара й початок третьої ·
з середини третьої пари — **кожен ділиться результатом**

П'ять тижнів ви розпаралелювали. Сьогодні з'ясуєте, що найбільший виграш дає
**не паралелізм**, а прибирання інтерпретатора з гарячого циклу.

## Що має бути наприкінці

- `4-numba/numba_versiya.py` — `@njit` і `@njit(parallel=True)`, **точний збіг** з еталоном,
  компіляція заміряна **окремо**;
- `4-numba/numpy_versiya.py` — векторизована версія, **пораховані розбіжні точки**;
- у `zamiry.md` — таблиця всіх реалізацій від практичної 02;
- `4-numba/vysnovky.md` — чому векторизація дала менше за компіляцію;
- усе на GitHub, рядок із результатом — у чаті.

**Мінімум для зарахування** — кроки 0–2: обидві версії Numba працюють, точний збіг,
компіляція заміряна окремо.

**Контрольні точки:** 12:30 — крок 0 · 12:50 — крок 1 · 13:00 — крок 2 · 13:30 — крок 3 (кінець другої пари) ·
14:00 — крок 6, `push` і рядок у чат · 14:10 — ділимось результатами.

Застрягли більше ніж на 5 хвилин — напишіть у чат номер кроку й **скопійований** текст помилки.

---

## Крок 0. Python, встановлення, копія коду (5 хв)

Встановлювати краще ще на першій парі — завантаження ~60 МБ.

```
python --version
python -m pip install numpy numba
python -c "import numpy, numba; print(numpy.__version__, numba.__version__)"
```

⚠️ Numba підтримує **Python 3.10–3.14**. `python --version` показує 3.15 — див. «Якщо щось пішло не так».

```
cd rspo-2026
git pull
copy 1-poslidovno\mandelbrot.py 4-numba\numba_versiya.py
```

(На macOS / Linux: `cp 1-poslidovno/mandelbrot.py 4-numba/numba_versiya.py`.)

✔ Друкуються дві версії, наприклад `2.5.3 0.67.0`.

## Крок 1. `@njit` (20 хв)

У `numba_versiya.py` лишіть константи, `ryadok`, `poslidovno` і `zamir` з тижня 2. Додайте на початок:

```python
import numpy as np
from numba import njit, prange
```

Нижче — та сама задача однією функцією, що повертає масив. Цикл — **ваш із тижня 2**, змінюється лише обгортка:

```python
@njit
def mandelbrot_numba(W, H, MAX_ITER, XMIN, XMAX, YMIN, YMAX):
    out = np.empty((H, W), dtype=np.int32)
    for y in range(H):
        cy = YMIN + (YMAX - YMIN) * y / H
        for x in range(W):
            cx = XMIN + (XMAX - XMIN) * x / W
            zx = 0.0
            zy = 0.0
            n = 0
            while zx * zx + zy * zy <= 4.0 and n < MAX_ITER:
                zx, zy = zx * zx - zy * zy + cx, 2.0 * zx * zy + cy
                n += 1
            out[y, x] = n
    return out
```

Блок запуску:

```python
if __name__ == "__main__":
    t_base, chasy, base = zamir(poslidovno, 1)       # чистий Python: один прогін, він довгий
    base = np.array(base)
    ARGS = (W, H, MAX_ITER, XMIN, XMAX, YMIN, YMAX)

    t0 = perf_counter()
    mandelbrot_numba(*ARGS)                           # перший виклик = компіляція
    print("компіляція @njit:", round(perf_counter() - t0, 2), "с")

    t, chasy, r = zamir(mandelbrot_numba, 3, *ARGS)
    assert np.array_equal(r, base), "результат розійшовся з еталоном"
    print("@njit", [round(c, 4) for c in chasy], "прискорення", round(t_base / t))
```

✔ `assert` мовчить — **точний збіг**.
✔ Компіляція — пів секунди–секунда; сам `@njit` — **у 40–80 разів** швидше за чистий Python.

## Крок 2. `prange` (10 хв)

Скопіюйте функцію під іншою назвою й змініть два місця:

```python
@njit(parallel=True)
def mandelbrot_prange(W, H, MAX_ITER, XMIN, XMAX, YMIN, YMAX):
    out = np.empty((H, W), dtype=np.int32)
    for y in prange(H):                  # було range
        ...                              # далі без змін
```

Той самий замір: окремо перший виклик, потім `zamir` і `np.array_equal`.

✔ Точний збіг. Прискорення відносно `@njit` — приблизно як процеси відносно послідовної версії на тижні 4.

```
git add 4-numba
git commit -m "практична 06: Numba njit і prange"
git push
```

✔ **Мінімум для зарахування — ви тут.**

## Крок 3. Векторизована версія (25 хв)

Новий файл `4-numba/numpy_versiya.py`. Скопіюйте константи, `ryadok` і `poslidovno` з тижня 2.

```python
import numpy as np
from time import perf_counter

def mandelbrot_numpy():
    cx, cy = np.meshgrid(np.linspace(XMIN, XMAX, W, endpoint=False),
                         np.linspace(YMIN, YMAX, H, endpoint=False))
    zx = np.zeros((H, W))
    zy = np.zeros((H, W))
    out = np.full((H, W), MAX_ITER, dtype=np.int32)
    aktyvni = np.ones((H, W), dtype=bool)          # точки, що ще не вилетіли
    for n in range(MAX_ITER):
        zx_n = zx * zx - zy * zy + cx
        zy_n = 2.0 * zx * zy + cy
        zx = np.where(aktyvni, zx_n, zx)
        zy = np.where(aktyvni, zy_n, zy)
        vyletily = aktyvni & (zx * zx + zy * zy > 4.0)
        out[vyletily] = n + 1
        aktyvni &= ~vyletily
        if not aktyvni.any():
            break
    return out

if __name__ == "__main__":
    base = np.array(poslidovno())
    t = perf_counter()
    r = mandelbrot_numpy()
    print("NumPy:", round(perf_counter() - t, 2), "с")
    print("розбіжних точок:", int((r != base).sum()), "із", base.size)
```

Спершу приберіть `endpoint=False` з обох `linspace` — і подивіться, скільки точок розійдеться. Потім поверніть.

✔ Без `endpoint=False` — **тисячі** розбіжних точок. З ним — **0, 1 або кілька**, усі на межі фрактала.
✔ Час — від ×0,8 до ×1,5 відносно чистого Python: майже нічого.

## Крок 4. Таблиця всіх реалізацій (15 хв)

У `zamiry.md` — одна таблиця, мінімуми з ваших практичних:

```markdown
## Усі реалізації · процесор … · ядер фізичних / логічних …

| Реалізація | Час, с | Прискорення | Збіг з еталоном |
|---|---|---|---|
| послідовно (02) | | ×1 | — |
| потоки, max (03) | | | так |
| процеси, max (04) | | | так |
| NumPy (06) | | | N розбіжних точок |
| Numba @njit (06) | | | так |
| Numba prange (06) | | | так |
```

```
git add zamiry.md 4-numba
git commit -m "практична 06: векторизація і таблиця"
git push
```

## Крок 5. Висновки (15 хв)

`4-numba/vysnovky.md` — 5–7 речень **своїми словами й зі своїми числами**:

1. Скільки дав `@njit` на одному ядрі — і скільки дали процеси на всіх ядрах?
2. Чому векторизація дала так мало? (Що відбувається з точками, які вже вилетіли?)
3. Чому з'явились розбіжні точки — і чому в Numba їх немає?
4. Що дав `prange` понад `@njit` — і чому це число схоже на прискорення процесів?
5. Що б ви робили першим, прискорюючи власний код: розпаралелювали чи компілювали?

## Крок 6. Здати (5 хв)

```
git add 4-numba
git commit -m "практична 06: висновки"
git push
```

Скиньте в чат один рядок:

```
ядер 16 · база 10.9 с · процеси ×5.9 · njit ×63 · prange ×378 · NumPy ×1.5 · розбіжних точок 1
```

---

## Якщо щось пішло не так

| Що бачите | Що це означає | Що робити |
|---|---|---|
| `python --version` → 3.15, `pip install numba` падає зі збиранням `llvmlite` | для Python 3.15 Numba ще немає | `py install 3.14`; далі `py -3.14 -m pip install numpy numba` і запуск `py -3.14 4-numba\numba_versiya.py` |
| `No module named 'numba'`, хоча встановлювали | pip поставив в інший Python | `python -m pip install numpy numba` — тим самим `python`, яким запускаєте |
| `TypingError: Failed in nopython mode` | у `@njit` щось, крім чисел і масивів | прибрати зі функції списки списків, `print`, виклики своїх звичайних функцій |
| «Numba повільніша за Python» | у замір потрапила компіляція | спершу один виклик окремо, потім `zamir` |
| `AssertionError` у Numba | цикл відрізняється від тижня 2 | звірити формули `cx`, `cy` і межі з `mandelbrot.py` |
| `ValueError: The truth value of an array ... is ambiguous` | `assert r == base` на масивах | `np.array_equal(r, base)` |
| тисячі розбіжних точок у NumPy | `linspace` без `endpoint=False` | додати `endpoint=False` в обидва |
| NumPy-версія з'їдає всю пам'ять | зображення завелике для масивів | зменшити `W`, `H` для цієї версії й записати це в таблицю |

---

## ⭐ Хто закінчив раніше

По черзі, скільки встигнете. Результати — у кінець `vysnovky.md`.

**⭐1. Коли компіляція окупається (10 хв).** На зображенні 100×60 заміряйте чистий Python,
компіляцію і `@njit`. Скільки викликів треба, щоб компіляція окупилась? А на вашому розмірі?

**⭐2. `fastmath` (10 хв).** `@njit(fastmath=True)` — що з часом? Порахуйте розбіжні точки
відносно звичайного `@njit`. Поясніть, чому так може бути.

**⭐3. Коли NumPy обганяє Numba (20 хв).** Множення двох матриць 400×400: `a @ b` у NumPy
проти потрійного циклу в `@njit`. У скільки разів? Чому тут векторизація виграє, а на Мандельброті — ні?

**⭐4. Справжня задача: з якого розміру `prange` виграє (30+ хв).** Заміряйте `@njit` і
`@njit(parallel=True)` на розмірах 2×2, 4×3, 10×6, 30×20, 300×200, 1200×800. На крихітних
розмірах час — мікросекунди, тож прогонів треба сотні, беріть мінімум. З якого розміру
`prange` починає виграти? Порівняйте цей поріг із вартістю пулу процесів із тижня 4
і поясніть, звідки така різниця.

---

## Не були на парі або навчаєтесь асинхронно

Ті самі кроки 0–6 — **до початку наступного заняття**. Замість показу на парі
допишіть у `vysnovky.md` ще один абзац: що здивувало й на якому кроці було найважче.
Рядок із результатом — у чат, як усі.

---

## Критерії — до 8 балів

| Балів | За що |
|:---:|---|
| 2 | Обидві версії Numba працюють, точний збіг |
| 2 | Компіляція заміряна окремо від виконання |
| 2 | Векторизована версія + підраховані розбіжні точки |
| 2 | Пояснення, **чому саме тут** векторизація дала менше |

Зробили на парі — домашнього немає.
