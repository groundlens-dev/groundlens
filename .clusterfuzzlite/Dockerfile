# ClusterFuzzLite build image for Groundlens.
# Digest pinned for OpenSSF Scorecard (pinned-dependencies).
FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:093721649cdd0d15c1e97eb905ed94079c09ffc8b3341c5dc42957b92f1b388f
COPY . $SRC/groundlens
WORKDIR $SRC/groundlens
COPY .clusterfuzzlite/build.sh $SRC/build.sh
