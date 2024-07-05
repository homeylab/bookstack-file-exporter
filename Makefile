## DOCKER BUILD VARS
BASE_IMAGE=python
BASE_IMAGE_TAG=3.12.4-slim-bookworm
IMAGE_NAME=homeylab/bookstack-file-exporter
# keep this start sequence unique (IMAGE_TAG=)
# github actions will use this to create a tag
IMAGE_TAG=main
DOCKER_WORK_DIR=/export
DOCKER_CONFIG_DIR=/export/config
DOCKER_EXPORT_DIR=/export/dump

pip_build:
	python -m pip install .

pip_local_dev:
	python -m pip install -e .

build:
	python -m pip install --upgrade build
	python -m build

upload_testpypi:
	python -m pip install --upgrade twine
	python -m twine upload --repository testpypi dist/*

# extra-url is for dependencies using real pypi
download_testpypi:
	python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple bookstack-file-exporter

docker_build: 
	docker buildx build \
	--platform linux/amd64,linux/arm64 \
	--output "type=image,push=false" \
	--build-arg BASE_IMAGE=${BASE_IMAGE} \
	--build-arg BASE_IMAGE_TAG=${BASE_IMAGE_TAG} \
	--build-arg DOCKER_WORK_DIR=${DOCKER_WORK_DIR} \
	--build-arg DOCKER_CONFIG_DIR=${DOCKER_CONFIG_DIR} \
	--build-arg DOCKER_EXPORT_DIR=${DOCKER_EXPORT_DIR} \
	-t ${IMAGE_NAME}:${IMAGE_TAG} \
	--no-cache .

docker_build_latest:
	docker buildx build \
	--platform linux/amd64,linux/arm64 \
	--output "type=image,push=true" \
	--build-arg BASE_IMAGE=${BASE_IMAGE} \
	--build-arg BASE_IMAGE_TAG=${BASE_IMAGE_TAG} \
	--build-arg DOCKER_WORK_DIR=${DOCKER_WORK_DIR} \
	--build-arg DOCKER_CONFIG_DIR=${DOCKER_CONFIG_DIR} \
	--build-arg DOCKER_EXPORT_DIR=${DOCKER_EXPORT_DIR} \
	-t ${IMAGE_NAME}:${IMAGE_TAG} \
	-t ${IMAGE_NAME}:latest \
	--no-cache .

docker_push:
	docker push ${IMAGE_NAME}:${IMAGE_TAG}

docker_push_latest:
	docker push ${IMAGE_NAME} --all-tags

# add -i option due to bug in rancher desktop: https://github.com/rancher-sandbox/rancher-desktop/issues/3239
docker_test:
	docker run -i \
	-e LOG_LEVEL='debug' \
	--user 1000:1000 \
	-v ${CURDIR}/local/config.yml:/export/config/config.yml:ro \
	-v ${CURDIR}/bkps:/export/dump \
	${IMAGE_NAME}:${IMAGE_TAG}