FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Install system packages
RUN apt-get update && \
    apt-get install -y build-essential libpq-dev gcc curl && \
    apt-get clean

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 🔥 Copy .env before running collectstatic
COPY .env .env

# Copy project files
COPY . .

# Now Django can read .env during build
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "personal_bank.wsgi:application", "--bind", "0.0.0.0:8000"]
