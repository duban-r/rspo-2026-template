# ⭐ Варіант із Docker — для тих, у кого Docker уже встановлений.
# Один образ на всі ролі: брокер, працівник і координатор відрізняються лише командою.
FROM python:3.12-slim
WORKDIR /stend
COPY *.py ./
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
CMD ["python", "pratsivnyk.py"]
