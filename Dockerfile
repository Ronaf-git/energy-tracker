FROM python:3.11-slim

# Set environment variables for locale
ENV LANG=fr_FR.UTF-8
ENV LANGUAGE=fr_FR:fr
ENV LC_ALL=fr_FR.UTF-8

# Install system packages required for locales
RUN apt-get update && \
    apt-get install -y --no-install-recommends locales && \
    sed -i '/fr_FR.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen fr_FR.UTF-8 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

CMD ["python", "app.py"]
