FROM python:3.11-slim

WORKDIR /app

COPY admin_ui/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY admin_ui /app/admin_ui

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "admin_ui.main:app", "--host", "0.0.0.0", "--port", "8000"]
