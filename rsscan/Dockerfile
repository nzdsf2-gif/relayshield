# The highest-leverage artifact in this repo. One image is consumed by Bitbucket
# Pipes, Tekton, Drone, Woodpecker, Harness, Argo Workflows and the generic
# "run a container" step every other CI system has -- instead of a bespoke
# integration per platform.
FROM python:3.12-alpine

# git is required: rsscan shells out to `git diff`. Alpine's python image has no
# git, and the failure would otherwise surface as a confusing FileNotFoundError.
RUN apk add --no-cache git

WORKDIR /src
COPY pyproject.toml README.md ./
COPY rsscan ./rsscan
RUN pip install --no-cache-dir .

# Every CI system mounts the checkout somewhere different; /workspace is the
# most common convention and can be overridden with -w.
WORKDIR /workspace

# Repos are owned by the CI user, not root, and git refuses to operate on a repo
# owned by another user. Without this every containerised run fails with
# "detected dubious ownership".
RUN git config --global --add safe.directory '*'

ENTRYPOINT ["rsscan"]
