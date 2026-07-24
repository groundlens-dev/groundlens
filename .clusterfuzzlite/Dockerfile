# ClusterFuzzLite build image for Groundlens.
FROM gcr.io/oss-fuzz-base/base-builder-python
COPY . $SRC/groundlens
WORKDIR $SRC/groundlens
COPY .clusterfuzzlite/build.sh $SRC/build.sh
