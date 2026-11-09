/* The probe of the RUN in progress (probe.h). */
#include "probe.h"

volatile probe_t probe;

void probe_begin(uint32_t wait_mode)
{
    probe_t clean = {0};
    clean.wait_mode = wait_mode;
    *(probe_t *)&probe = clean;
}
