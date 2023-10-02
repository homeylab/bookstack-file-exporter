## DOCKER BUILD VARS
BASE_IMAGE=python
BASE_IMAGE_TAG=3.11-slim-bookworm
IMAGE_NAME=homeylab/bookstack-file-exporter
IMAGE_TAG=test
DOCKER_WORK_DIR=/export
DOCKER_CONFIG_DIR=/export/config
DOCKER_EXPORT_DIR=/export/dump

pip_build:
	pip install .

pip_local_dev:
	pip install -e .

docker_build: 
	docker buildx build \
	--build-arg BASE_IMAGE=${BASE_IMAGE} \
	--build-arg BASE_IMAGE_TAG=${BASE_IMAGE_TAG} \
	--build-arg DOCKER_WORK_DIR=${DOCKER_WORK_DIR} \
	--build-arg DOCKER_CONFIG_DIR=${DOCKER_CONFIG_DIR} \
	--build-arg DOCKER_EXPORT_DIR=${DOCKER_EXPORT_DIR} \
	-t ${IMAGE_NAME}:${IMAGE_TAG} \
	--no-cache .

docker_push:
	docker push ${IMAGE_NAME}:${IMAGE_TAG}

# add -i option due to bug in rancher desktop: https://github.com/rancher-sandbox/rancher-desktop/issues/3239
docker_test:
	docker run -i \
	-e LOG_LEVEL='debug' \
	--user 1000:1000 \
	-v ${CURDIR}/local/config.yml:/export/config/config.yml:ro \
	-v ${CURDIR}/bkps:/export/dump \
	${IMAGE_NAME}:${IMAGE_TAG}