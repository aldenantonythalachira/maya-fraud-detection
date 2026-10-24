FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements-core.txt ./
RUN pip install --no-cache-dir -r requirements-core.txt
COPY src ./src
COPY scripts ./scripts
COPY frontend ./frontend
COPY docs/evidence ./docs/evidence
COPY run_demo.py ./
# A reproducible synthetic demo model; not a production-bank-trained model.
RUN python scripts/bootstrap_v4.py && python scripts/train_wallet_bundle.py && useradd --uid 10001 --create-home maya && chown -R maya:maya /app
USER maya
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz',timeout=3)"
CMD ["python","run_demo.py","--host","0.0.0.0","--port","8000"]
