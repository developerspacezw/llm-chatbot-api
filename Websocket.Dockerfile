# Use a multi-stage build to reduce the final image size
FROM python:3.10-slim as builder

# Set the working directory
WORKDIR /app

# Install dependencies in a virtual environment
RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip && \
    pip install --no-cache-dir \
        websockets==13.0 \
        confluent-kafka==2.6.0 \
        python-dotenv==1.0.0 \
        elastic-apm==6.15.0

# Use a smaller base image for the final stage
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Ensure the virtual environment is activated
ENV PATH="/opt/venv/bin:$PATH"

# Copy the application code
COPY . .

# Expose the port the application will run on
EXPOSE 8001

# Set the default command to run the application
CMD ["python", "websockets.py"]