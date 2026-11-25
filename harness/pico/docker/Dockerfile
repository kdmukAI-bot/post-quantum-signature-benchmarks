# Build and flashing image for harness/pico (Waveshare RP2350 Touch LCD 2, RP2350 Arm
# Cortex-M33 cores). Every input is pinned:
#
#   base image         debian:12-slim by digest
#   Arm GNU toolchain  14.2.rel1 (arm-none-eabi GCC 14.2.1), checked against Arm's SHA-256
#   Pico SDK           2.3.1 (tag commit 079c6f39), with lib/tinyusb only (USB CDC stdio)
#   picotool           2.3.1 (tag commit 20419364), built from source against the SDK
#   FreeRTOS-Kernel    raspberrypi/FreeRTOS-Kernel main at 4f7299d6 (RP2350_ARM_NTZ port)
#
# Build (from the workspace root):
#   docker build -t pqb-rp2350:sdk2.3.1-gcc14.2 harness/pico/docker
FROM debian@sha256:7b140f374b289a7c2befc338f42ebe6441b7ea838a042bbd5acbfca6ec875818

ARG ARM_TC=14.2.rel1
ARG ARM_TC_SHA256=62a63b981fe391a9cbad7ef51b17e49aeaa3e7b0d029b36ca1e9c3b2a9b78823
ARG PICO_SDK_TAG=2.3.1
ARG PICO_SDK_COMMIT=079c6f39023649b154152db30f1d781e884879bc
ARG PICOTOOL_TAG=2.3.1
ARG PICOTOOL_COMMIT=2041936441b48a3cc53ae3da9e805229fe8f4e18
ARG FREERTOS_COMMIT=4f7299d6ea746b27a9dd19e87af568e34bd65b15

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl xz-utils git cmake make ninja-build python3 g++ \
        pkg-config libusb-1.0-0-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/tc.tar.xz \
        "https://developer.arm.com/-/media/Files/downloads/gnu/${ARM_TC}/binrel/arm-gnu-toolchain-${ARM_TC}-x86_64-arm-none-eabi.tar.xz" \
    && echo "${ARM_TC_SHA256}  /tmp/tc.tar.xz" | sha256sum -c - \
    && mkdir -p /opt/arm-gnu-toolchain \
    && tar -xJf /tmp/tc.tar.xz -C /opt/arm-gnu-toolchain --strip-components=1 \
    && rm /tmp/tc.tar.xz \
    && rm -rf /opt/arm-gnu-toolchain/share/doc
ENV PATH=/opt/arm-gnu-toolchain/bin:$PATH

RUN git clone --depth 1 --branch "${PICO_SDK_TAG}" https://github.com/raspberrypi/pico-sdk.git /opt/pico-sdk \
    && test "$(git -C /opt/pico-sdk rev-parse HEAD)" = "${PICO_SDK_COMMIT}" \
    && git -C /opt/pico-sdk submodule update --init --depth 1 lib/tinyusb
ENV PICO_SDK_PATH=/opt/pico-sdk

RUN git clone --depth 1 --branch "${PICOTOOL_TAG}" https://github.com/raspberrypi/picotool.git /tmp/picotool \
    && test "$(git -C /tmp/picotool rev-parse HEAD)" = "${PICOTOOL_COMMIT}" \
    && cmake -S /tmp/picotool -B /tmp/picotool/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /tmp/picotool/build \
    && cmake --install /tmp/picotool/build \
    && rm -rf /tmp/picotool

RUN git init -q /opt/FreeRTOS-Kernel \
    && git -C /opt/FreeRTOS-Kernel remote add origin https://github.com/raspberrypi/FreeRTOS-Kernel.git \
    && git -C /opt/FreeRTOS-Kernel fetch -q --depth 1 origin "${FREERTOS_COMMIT}" \
    && git -C /opt/FreeRTOS-Kernel checkout -q FETCH_HEAD
ENV FREERTOS_KERNEL_PATH=/opt/FreeRTOS-Kernel

WORKDIR /work
