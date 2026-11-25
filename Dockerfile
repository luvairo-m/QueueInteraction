FROM python:3.12-slim AS common

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM common AS worker
COPY queue_interaction/ queue_interaction/
CMD ["python", "-m", "queue_interaction.worker"]

FROM common AS api
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY queue_interaction/ queue_interaction/
COPY web/ web/
COPY examples/job.json examples/job.json
CMD ["python", "-m", "uvicorn", "queue_interaction.api:app", "--host", "0.0.0.0", "--port", "8000"]
