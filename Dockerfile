FROM python:3.11-slim

# Establecer directorio de trabajo
WORKDIR /app

# Copiar solo requirements.txt primero
COPY requirements.txt .

# Instalar dependencias antes de copiar el resto del código (esto se cachea si no cambian las dependencias)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código después de instalar dependencias
COPY . .

# Comando por defecto
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
