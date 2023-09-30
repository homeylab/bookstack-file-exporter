ARG BASE_IMAGE=python
ARG BASE_IMAGE_TAG=3.11-slim-python

FROM ${BASE_IMAGE}:${BASE_IMAGE_TAG}

# Get security updates and clean up apt cache for smaller size
RUN apt update -y && apt upgrade -y && \
    apt install dumb-init && \
    rm -rf /var/lib/apt/lists/*

ARG DOCKER_WORK_DIR
ARG DOCKER_CONFIG_DIR
ARG DOCKER_EXPORT_DIR

ENV DOCKER_CONFIG_DIR=${DOCKER_CONFIG_DIR}
ENV DOCKER_EXPORT_DIR=${DOCKER_EXPORT_DIR}

WORKDIR ${DOCKER_WORK_DIR}

COPY . .

RUN pip install .

RUN mkdir -p ${DOCKER_CONFIG_DIR} && \
    mkdir -p ${DOCKER_EXPORT_DIR}

USER nobody

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD [ "./entrypoint.sh" ]