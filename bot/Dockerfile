# Base Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app/
COPY requirements.txt /app/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Environment variables
ENV PYTHONUNBUFFERED=1

# Command to run the bot
CMD ["python", "bot/bot.py"]
