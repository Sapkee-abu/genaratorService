FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_DISABLE_XET=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.0+cpu \
    && pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --system --uid 10001 generator \
    && mkdir -p /app/output /app/models \
    && chown -R generator:generator /app/output /app/models
USER generator
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8010"]

