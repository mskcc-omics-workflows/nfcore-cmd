# Dockerfile to create container with {{ your_module_name }}
# Push to mpathdms/{{ your_module_name }}:<VER>

FROM # TODO
LABEL authors="DMS" \
    description="Docker image containing {{ your_module_name }}"

# 'ps' command is needed by some nextflow executions to collect system stats
# Install procps and clean apt cache
RUN apt-get update \
    && apt-get install -y \
    procps \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*
