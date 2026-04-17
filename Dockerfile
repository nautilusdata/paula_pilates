# Imagen base Python slim
FROM python:3.12-slim

# Variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el proyecto
COPY academia/ .

# Recolectar estáticos
RUN python manage.py collectstatic --noinput

# Puerto
EXPOSE 8080

# Arrancar con gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "academia.wsgi:application"]
