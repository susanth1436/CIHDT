# The CIHDT operator console as a container.
#
# Built for Hugging Face Spaces (Docker SDK), which serves port 7860 and runs
# the container as uid 1000, but there is nothing Spaces-specific here: any
# container host works, and PORT overrides the exposed port.
#
#   docker build -t cihdt .
#   docker run -p 7860:7860 cihdt
#
# Live USB mode is unavailable in a container -- enumeration goes through
# Windows WMI, and a server has no peripherals attached regardless. The
# console detects this, says so on the telemetry-source page, and runs the
# simulated fleet.

FROM python:3.13-slim

# Non-root, and uid 1000 because that is the user Spaces runs as.
RUN useradd --create-home --uid 1000 cihdt

WORKDIR /app

# Dependencies first, so edits to the source do not invalidate the layer.
COPY --chown=cihdt:cihdt requirements-web.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements-web.txt

COPY --chown=cihdt:cihdt cihdt/ ./cihdt/
COPY --chown=cihdt:cihdt run.py cli.py README.md ./

# The database and the model registry are written at run time. They live
# outside the application directory so the image stays reusable and a
# read-only root filesystem does not break startup.
ENV CIHDT_DATA_DIR=/home/cihdt/state/data \
    CIHDT_ARTIFACTS_DIR=/home/cihdt/state/artifacts \
    CIHDT_SEED=1337 \
    CIHDT_REQUIRE_REGISTRATION_CODE=0 \
    PORT=7860 \
    PYTHONUNBUFFERED=1
RUN mkdir -p /home/cihdt/state/data /home/cihdt/state/artifacts/models \
 && chown -R cihdt:cihdt /home/cihdt/state

USER cihdt
EXPOSE 7860

# run.py reads PORT and binds every interface when it is set.
CMD ["python", "run.py"]
