FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements-web.txt ./requirements-web.txt
RUN pip install --no-cache-dir -r requirements-web.txt

# Copy application code only. The desktop user's live database and local settings
# are deliberately not included in the image.
COPY bookkeeping/ ./bookkeeping/

RUN useradd --system --uid 10001 --create-home ledger \
    && mkdir -p /var/lib/household-bookkeeping \
    && chown -R ledger:ledger /app /var/lib/household-bookkeeping
USER 10001:10001

EXPOSE 8000
CMD ["python", "-m", "bookkeeping.web", "--host", "0.0.0.0", "--port", "8000", "--data-dir", "/var/lib/household-bookkeeping"]
