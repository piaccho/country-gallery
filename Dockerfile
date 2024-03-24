# docker build -t country_gallery .                             # Build the image
# docker run -p 8080:8080 country_gallery                       # Run the container
# docker run -p 8080:8080 --env-file .env country_gallery       # Run the container with environment variable

FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY ./app /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{$PORT}"]
