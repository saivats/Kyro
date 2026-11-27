FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN apt-get update && apt-get install --no-install-recommends -y libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements-demo.txt .
RUN pip install --no-cache-dir -r requirements-demo.txt
COPY app/ app/
COPY demo.py .
COPY demo_templates/ demo_templates/
COPY static/ static/
EXPOSE 5000
CMD ["python","-m","flask","--app","demo:create_demo_app","run","--host=0.0.0.0","--port=5000","--no-debugger","--no-reload"]
