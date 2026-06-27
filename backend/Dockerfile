FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . /app
RUN chmod +x /app/start.sh

EXPOSE 8000
CMD ["/app/start.sh"]
