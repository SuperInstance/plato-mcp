FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN pip install -e .
EXPOSE 8300
CMD ["python3", "-m", "plato_mcp.cli", "--host", "0.0.0.0", "--port", "8300"]
