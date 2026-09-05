# FROM python:3.12-slim

# WORKDIR /app

# # Required system dependencies
# RUN apt-get update && apt-get install -y \
#     wget \
#     gnupg \
#     ca-certificates \
#     libpq-dev \
#     gcc \
#     && rm -rf /var/lib/apt/lists/*

# # Install Google Chrome signing key
# RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | \
#     gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg

# # Add Google Chrome repository
# RUN echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
#     http://dl.google.com/linux/chrome/deb/ stable main" \
#     > /etc/apt/sources.list.d/google-chrome.list

# # Install Google Chrome
# RUN apt-get update && \
#     apt-get install -y google-chrome-stable && \
#     rm -rf /var/lib/apt/lists/*

# # Copy requirements
# COPY requirements.txt .

# # Install Python dependencies
# RUN pip install --no-cache-dir --upgrade pip && \
#     pip install --no-cache-dir -r requirements.txt

# # Copy application
# COPY . .

# EXPOSE 8000

# ENV PORT=8000

# CMD ["streamlit", "run", "IQEA.py", "--server.port=8000", "--server.address=0.0.0.0"]
# FROM python:3.12-slim

# WORKDIR /app

# # --------------------------------------------------
# # Install only required Linux dependencies
# # Chrome + Selenium/Playwright dependencies
# # --------------------------------------------------
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     wget \
#     gnupg \
#     ca-certificates \
#     libnss3 \
#     libgbm1 \
#     libx11-xcb1 \
#     libxcomposite1 \
#     libxdamage1 \
#     libxrandr2 \
#     libasound2 \
#     libgtk-3-0 \
#     && rm -rf /var/lib/apt/lists/*


# # --------------------------------------------------
# # Install Google Chrome
# # --------------------------------------------------
# RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | \
#     gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
#     echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
#     https://dl.google.com/linux/chrome/deb/ stable main" \
#     > /etc/apt/sources.list.d/google-chrome.list && \
#     apt-get update && \
#     apt-get install -y --no-install-recommends google-chrome-stable && \
#     rm -rf /var/lib/apt/lists/*
# RUN apt-get update && apt-get install -y \
#     tesseract-ocr \
#     && rm -rf /var/lib/apt/lists/*


# # --------------------------------------------------
# # Copy requirements first
# # This allows Podman build caching
# # --------------------------------------------------
# COPY requirements.txt .


# # --------------------------------------------------
# # Install Python dependencies
# # --------------------------------------------------
# RUN pip install --no-cache-dir -r requirements.txt


# # ==================================================
# # COPY APPLICATION FILES
# # ==================================================

# # Main Python files
# COPY IQEA.py .
# COPY accuracy.py .
# COPY action_new_xpath.py .
# COPY action_new_xpath_subway.py .
# COPY action_new_xpath_subway_TMT.py .
# COPY api_validator.py .
# COPY chat_agent.py .
# COPY iqea_ui_prototype.py .
# COPY llm_test.py .
# COPY locustfile.py .
# COPY token_check_dummy.py .


# # --------------------------------------------------
# # Application folders
# # --------------------------------------------------
# COPY accelerator ./accelerator
# COPY chatbot ./chatbot
# COPY config ./config
# COPY data ./data
# COPY desktop ./desktop
# COPY generated_features ./generated_features
# COPY generated_xpath_details ./generated_xpath_details
# COPY Input ./Input
# COPY iqea_mobile ./iqea_mobile
# COPY pbi_validator ./pbi_validator
# COPY prompt_collection ./prompt_collection
# COPY recorded_steps ./recorded_steps
# COPY Self_healing_web_application ./Self_healing_web_application
# COPY utilities ./utilities


# # --------------------------------------------------
# # Streamlit configuration
# # --------------------------------------------------
# COPY .streamlit ./.streamlit


# # --------------------------------------------------
# # Environment configuration
# # --------------------------------------------------
# ENV PORT=8000
# ENV PYTHONUNBUFFERED=1
# ENV PYTHONDONTWRITEBYTECODE=1

# # Chrome configuration
# ENV CHROME_BIN=/usr/bin/google-chrome
# ENV CHROME_PATH=/usr/bin/google-chrome


# # --------------------------------------------------
# # Expose Streamlit port
# # --------------------------------------------------
# EXPOSE 8000


# # --------------------------------------------------
# # Start application
# # --------------------------------------------------
# CMD ["streamlit", "run", "IQEA.py", "--server.port=8000", "--server.address=0.0.0.0"]

FROM python:3.12-slim

WORKDIR /app

# --------------------------------------------------
# Install system dependencies
# Chrome + Selenium + Tesseract
# --------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    tesseract-ocr \
    libnss3 \
    libgbm1 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libasound2 \
    libgtk-3-0 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdrm2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------
# Install Google Chrome
# --------------------------------------------------
RUN wget -q -O /tmp/google-chrome-key.pub \
    https://dl.google.com/linux/linux_signing_key.pub && \
    gpg --dearmor \
    -o /usr/share/keyrings/google-chrome.gpg \
    /tmp/google-chrome-key.pub && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/* /tmp/google-chrome-key.pub

# --------------------------------------------------
# Copy requirements
# --------------------------------------------------
COPY requirements.txt .

# --------------------------------------------------
# Install Python dependencies
# --------------------------------------------------
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------------------------------
# Copy application files
# --------------------------------------------------
COPY IQEA.py .
COPY accuracy.py .
COPY action_new_xpath.py .
COPY action_new_xpath_subway.py .
COPY action_new_xpath_subway_TMT.py .
COPY api_validator.py .
COPY chat_agent.py .
COPY iqea_ui_prototype.py .
COPY llm_test.py .
COPY locustfile.py .
COPY token_check_dummy.py .

# --------------------------------------------------
# Copy application folders
# --------------------------------------------------
COPY accelerator ./accelerator
COPY chatbot ./chatbot
COPY config ./config
COPY data ./data
COPY desktop ./desktop
COPY generated_features ./generated_features
COPY generated_xpath_details ./generated_xpath_details
COPY Input ./Input
COPY iqea_mobile ./iqea_mobile
COPY pbi_validator ./pbi_validator
COPY prompt_collection ./prompt_collection
COPY recorded_steps ./recorded_steps
COPY Self_healing_web_application ./Self_healing_web_application
COPY utilities ./utilities

# --------------------------------------------------
# Streamlit configuration
# --------------------------------------------------
COPY .streamlit ./.streamlit

# --------------------------------------------------
# Environment variables
# --------------------------------------------------
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROME_PATH=/usr/bin/google-chrome

# --------------------------------------------------
# Expose Streamlit port
# --------------------------------------------------
EXPOSE 8000

# --------------------------------------------------
# Start Streamlit
# --------------------------------------------------
CMD ["python", "-m", "streamlit", "run", "IQEA.py", "--server.port=8000", "--server.address=0.0.0.0"]