#----------------------------------------------------------------------------
# Driver Runner (docs/plan/driver_runner_plan.md J1): an MLEK out-of-tree use case. TensorFlow Lite Micro only; no model
# is generated or linked: the Vela output arrives over UART at run time (DRWL, workload.h).
#----------------------------------------------------------------------------
set(${use_case}_ML_FRAMEWORK "TensorFlowLiteMicro")
if (NOT ${use_case}_ML_FRAMEWORK STREQUAL ${ML_FRAMEWORK})
    set(${use_case}_supports_${ML_FRAMEWORK} OFF)
    return()
endif ()
set(${use_case}_supports_${ML_FRAMEWORK} ON)

# Tensor arena size: the same as MLEK inference_runner's build option (0x00200000) for every model.
USER_OPTION(${use_case}_ACTIVATION_BUF_SZ "Tensor arena size, as MLEK inference_runner" 0x00200000 STRING)
USER_OPTION(${use_case}_BUILD_ID "Driver runner build id" 0x44525652 STRING)
set(${use_case}_COMPILE_DEFS "DRV_BUILD_ID=${${use_case}_BUILD_ID}")
list(APPEND ${use_case}_LINK_LIBS mlek::ml_framework_tflm)

# Reused unchanged from the legacy runner tree: DWT timestamps and the PMU register map.
set(DRV_COMMON_DIR ${CMAKE_CURRENT_LIST_DIR}/../../../common)
include_directories(${DRV_COMMON_DIR})
list(APPEND SRC_APPLICATION ${DRV_COMMON_DIR}/timing.c)
