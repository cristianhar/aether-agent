FROM python:3.12-slim

# Evitar prompts interactivos
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Instalar utilidades básicas (git, ripgrep, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ripgrep \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copiar dependencias e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente
COPY . .

# Directorio de trabajo montable
VOLUME ["/workspace/project"]

# Variable de entorno de Ollama por defecto
ENV OLLAMA_HOST=http://host.docker.internal:11434

CMD ["python", "main.py"]
