# Digest reported by OpenSSF Scorecard. Dependabot bumps it; a tag here would
# mean the fuzzer builds against different code week to week.
FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:6b2b3a7e4a2da50de47f94925cffbe34747e1aae4f33d7f07ba6c681dd648b23

COPY . $SRC/groundlens
COPY .clusterfuzzlite/build.sh $SRC/build.sh
WORKDIR $SRC/groundlens
