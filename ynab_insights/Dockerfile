FROM python:3.12-slim

WORKDIR /service

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

EXPOSE 8000

RUN useradd --create-home --shell /bin/bash app && chown -R app /service
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
