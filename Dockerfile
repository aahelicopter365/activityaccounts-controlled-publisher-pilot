FROM python:3.13-slim
RUN useradd --uid 10001 --create-home publisher && mkdir /app /data && chown publisher:publisher /app /data
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY __init__.py app.py contract.py receipts.py /app/external_test/
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AA_EXTERNAL_RECEIPTS_DB=/data/receipts.sqlite
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "external_test.app:configured_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log", "--log-level", "warning"]
