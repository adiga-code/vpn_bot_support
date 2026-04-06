# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код приложения
COPY . .

# Создаем директорию для БД (если не существует)
RUN mkdir -p /app

# Указываем порт
EXPOSE 8009

# Запускаем приложение
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]