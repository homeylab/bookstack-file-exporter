ARG BASE_IMAGE=python
ARG BASE_IMAGE_TAG=3.12.4-slim-bookworm

FROM ${BASE_IMAGE}:${BASE_IMAGE_TAG}

LABEL \
    org.opencontainers.image.title="bookstack-file-exporter" \
    org.opencontainers.image.description="Page asset and content exporter for Bookstack" \
    org.opencontainers.image.source="https://github.com/homeylab/bookstack-file-exporter"

# Get security updates and clean up apt cache for smaller size
RUN apt update -y && apt upgrade -y && \
    apt install dumb-init && \
    rm -rf /var/lib/apt/lists/*

# create docker user
RUN useradd -M -s /usr/sbin/nologin -u 33333 exporter

ARG DOCKER_WORK_DIR=/export
ARG DOCKER_CONFIG_DIR=/export/config
ARG DOCKER_EXPORT_DIR=/export/dump

ENV DOCKER_CONFIG_DIR=${DOCKER_CONFIG_DIR}
ENV DOCKER_EXPORT_DIR=${DOCKER_EXPORT_DIR}

WORKDIR ${DOCKER_WORK_DIR}

COPY . .

RUN pip install .

RUN install -d -m 0755 -o exporter -g exporter ${DOCKER_CONFIG_DIR} && \
    install -d -m 0755 -o exporter -g exporter ${DOCKER_EXPORT_DIR}

USER exporter

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD [ "./entrypoint.sh" ]