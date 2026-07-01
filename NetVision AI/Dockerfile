FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping net-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app.py ./
COPY static ./static

EXPOSE 5000

CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "5000"]
