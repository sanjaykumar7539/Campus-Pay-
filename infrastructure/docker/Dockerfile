FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ENVIRONMENT=production
WORKDIR /srv/campuspay
COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip && python -m pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend ./backend
COPY frontend ./frontend
USER 10001:10001
WORKDIR /srv/campuspay/backend
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
