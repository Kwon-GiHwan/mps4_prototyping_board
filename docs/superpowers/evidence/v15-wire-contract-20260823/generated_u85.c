/*
 * Copyright (c) 2026, Arm Limited. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <stddef.h>
#include <string.h>
#include <stdbool.h>

#define TARGET
#include "logging.h"
#include "serial.h"

#include "ARMCM85.h"

#include "interface.h"
#include "u85.h"

/*****************************************************************************
 *                                Typedefs
 * **************************************************************************/

/*****************************************************************************
 *                                Macros
 * **************************************************************************/
#define TEST_PROT 0
#define TEST_CPM 1

#define V15_VARIANT_ID 1U
#define V15_U32_INVALID 0xFFFFFFFFU
#define V15_MAILBOX_VALID 0x5631344DU
#define V15_QSIZE_EXPECTED 0x00000110U
#define V15_ITERATION_BOUND 10000U
#define V15_APPENDIX_WORDS 34U

#define V15_STATUS_STATE 0x001U
#define V15_STATUS_IRQ_RAISED 0x002U
#define V15_STATUS_RESET 0x008U
#define V15_STATUS_CMD_END 0x020U
#define V15_STATUS_FAULT_MASK 0x314U

#define V15_MBOX_VARIANT_ID 0U
#define V15_MBOX_QSIZE_EXPECTED 1U
#define V15_MBOX_PRE_PROGRAM_STATUS 2U
#define V15_MBOX_PRE_SUBMIT_STATUS 3U
#define V15_MBOX_T_SUBMIT_AFTER_CMD 4U
#define V15_MBOX_T_PRIMARY_ENTRY 5U
#define V15_MBOX_T_FIRST_OBSERVATION 6U
#define V15_MBOX_PRIMARY_RESULT 7U
#define V15_MBOX_PRIMARY_ITERATIONS 8U
#define V15_MBOX_FIRST_QREAD 9U
#define V15_MBOX_FIRST_STATUS 10U
#define V15_MBOX_FIRST_Q_DONE 11U
#define V15_MBOX_FIRST_CMD_END_REACHED 12U
#define V15_MBOX_FIRST_IRQ_RAISED 13U
#define V15_MBOX_FIRST_STATE 14U
#define V15_MBOX_CONVERGENCE_RESULT 15U
#define V15_MBOX_CONVERGENCE_ITERATIONS 16U
#define V15_MBOX_CONVERGENCE_FINAL_QREAD 17U
#define V15_MBOX_CONVERGENCE_FINAL_STATUS 18U
#define V15_MBOX_CONVERGENCE_TIMEOUT 19U
#define V15_MBOX_FAILURE_PHASE 20U
#define V15_MBOX_FAILURE_REASON 21U
#define V15_MBOX_FAILURE_QREAD 22U
#define V15_MBOX_FAILURE_STATUS 23U
#define V15_MBOX_INSTALLED_VECTOR 24U
#define V15_MBOX_NVIC_ENABLED_BEFORE_SUBMIT 25U
#define V15_MBOX_NVIC_PENDING_AFTER_INITIAL_CLEAR 26U
#define V15_MBOX_NVIC_ACTIVE_BEFORE_SUBMIT 27U
#define V15_MBOX_IRQ_TRIGGERED_BEFORE_SUBMIT 28U
#define V15_MBOX_NVIC_PENDING_BEFORE_FINAL_CLEAR 29U
#define V15_MBOX_NVIC_PENDING_AFTER_FINAL_CLEAR 30U
#define V15_MBOX_NVIC_ACTIVE_AFTER_CLEANUP 31U
#define V15_MBOX_IRQ_TRIGGERED_AFTER_CLEANUP 32U
#define V15_MBOX_MAILBOX_VALID 33U

#define V15_PRIMARY_NOT_RUN 0U
#define V15_PRIMARY_OBSERVED 1U
#define V15_PRIMARY_TIMEOUT 2U
#define V15_PRIMARY_RESET 3U
#define V15_PRIMARY_FAULT 4U

#define V15_CONVERGENCE_NOT_RUN 0U
#define V15_CONVERGENCE_SUCCESS 1U
#define V15_CONVERGENCE_TIMEOUT 2U
#define V15_CONVERGENCE_RESET 3U
#define V15_CONVERGENCE_FAULT 4U

#define V15_PHASE_NONE 0U
#define V15_PHASE_PRE_PROGRAM 1U
#define V15_PHASE_PRE_SUBMIT 2U
#define V15_PHASE_PRIMARY 3U
#define V15_PHASE_CONVERGENCE 4U
#define V15_PHASE_CLEANUP 5U

#define V15_REASON_NONE 0U
#define V15_REASON_STATE_RUNNING 1U
#define V15_REASON_RESET_IN_PROGRESS 2U
#define V15_REASON_HARDWARE_FAULT 3U
#define V15_REASON_STALE_IRQ 4U
#define V15_REASON_STALE_CMD_END 5U
#define V15_REASON_QSIZE_MISMATCH 6U
#define V15_REASON_PRIMARY_TIMEOUT 7U
#define V15_REASON_CONVERGENCE_TIMEOUT 8U
#define V15_REASON_CLEANUP_INVARIANT 9U

#define V15_RET_SUCCESS 0
#define V15_RET_PRE_PROGRAM_FAILURE 1
#define V15_RET_PRE_SUBMIT_FAILURE 2
#define V15_RET_PRIMARY_TIMEOUT 3
#define V15_RET_RESET_IN_PROGRESS 4
#define V15_RET_HARDWARE_FAULT 5
#define V15_RET_CONVERGENCE_TIMEOUT 6
#define V15_RET_CLEANUP_INVARIANT 7

volatile uint32_t pmu_completion_visibility_v15_mailbox[34];

struct v15_observation_t {
    uint32_t result;
    uint32_t iterations;
    uint32_t qread;
    uint32_t status;
    uint32_t t_first;
};

void v15_mailbox_reset(void);
static void v15_mailbox_publish(void);
static void v15_publish_failure(uint32_t phase, uint32_t reason, uint32_t qread, uint32_t status);
static void v15_publish_cleanup_failure(uint32_t qread, uint32_t status);
static void v15_publish_success(void);
static void v15_publish_primary(const struct v15_observation_t *obs, uint32_t qsize_expected);
static void v15_primary_s5(uint32_t qsize_expected, struct v15_observation_t *obs);
static void v15_converge(uint32_t qsize_expected, struct v15_observation_t *obs);
#define VERIFY_OUTPUT 1
#define MAC_RAMP_VAR 2
#define NPU_ID 0X20007001

#define U85_BASE_ADDRESS 0x50004000

// Controls for sleep function
// Undefine BUSY_SLEEP to use ARM __wfi() function that
// puts host to sleep, until an interrupt arrives
#define BUSY_SLEEP
#define BUSY_SLEEP_TIMEOUT 10000

/*****************************************************************************
 *                                Local definitions
 * **************************************************************************/
static volatile bool irq_triggered = false;
static volatile bool irq_never_triggered = false;
static volatile uint16_t irq_history_mask = 0;

/*****************************************************************************
 *                           Local function definitions
 * **************************************************************************/
// Sleep function to wait for IRQ
static inline void sleep()
{
#if defined(BUSY_SLEEP)
  static volatile int i,j=0;
  for (i=0 ; i < BUSY_SLEEP_TIMEOUT; i++) {
    if (irq_triggered) {
      return;
    }
    j=j*i;
  }
#else
 // Use the ARM definfed __wfi() (wait for interrupt) function call and put the processor to
 // sleep until an interrupt is raised.
 // Customer needs to modify this function to do something else if the host should not sleep while
 // waiting for an interrupt from the NPU
  __wfi();

#endif
}

// Example functions to read and write to a given memory mapped register
static inline uint32_t read_reg(uint32_t address) {
    volatile uint32_t *reg = (uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + address);
    return *reg;
}

static inline void write_reg(uint32_t  address, uint32_t  value) {
    volatile uint32_t *reg = (uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + address);
    *reg = value;
}

// This is the irq_handler that reads out the status register and prints the contents and
// the history mask when an interrupt is raised. Customer needs to examine if the status
// registers shows that correct interrupt is raised and the history mask is updated
// Customer also needs to handle the irq as desired by modifying this function and remove the
// port_print calls as they are not typically used inside an irq handler
// This task also clears the CPM settings when called by writing all bits CMD_REG to zero except clear_IRQ
void u85_irq_handler()
{
    int32_t status_register = 0;
    status_register = read_reg(NPU_REG_STATUS);
    // Get the MASK bits into status_mask
    irq_history_mask = status_register >> 16;
    if ((status_register & 0x02)){
        printf("Got IRQ, History_mask is %x status_register is %x\n", irq_history_mask, status_register);
        printf("Expected History_mask is set in CMD0_NPU_OP_STOP of the corresponding cmd stream include file\n");
        irq_triggered = true;
        write_reg(NPU_REG_CMD, 2);
    }
}

static inline void wait_for_irq(void)
{
    while (false == irq_triggered) {
      sleep();
      if (!irq_triggered) {
        irq_never_triggered = true;
        printf("TEST FAILED: IRQ not triggered after timeout, Status reg is %x\n", read_reg(NPU_REG_STATUS));
        break;
      }
    }
    irq_triggered = false;
}

// Wait for NPU reset function that polls the status register to ensure reset is done
static uint32_t wait_for_reset(void)
{
    uint32_t status_register = 0;
    uint32_t reset_success = 0;

    //Wait until reset status indicates that reset has been completed
    for (int i = 0; i < 500; i++) {
        status_register = read_reg(NPU_REG_STATUS);
        if (0 == (status_register & 0x8)) {
            reset_success = 1;
            printf("Reset Success\n");
            break;
        }
    }

    return reset_success;
}

__attribute__((noinline))
void v15_mailbox_reset(void)
{
    for (uint32_t i = 0U; i < V15_APPENDIX_WORDS; ++i) {
        pmu_completion_visibility_v15_mailbox[i] = V15_U32_INVALID;
    }
    pmu_completion_visibility_v15_mailbox[V15_MBOX_MAILBOX_VALID] = 0U;
    __DSB();
}

__attribute__((noinline))
static void v15_mailbox_publish(void)
{
    __DSB();
    pmu_completion_visibility_v15_mailbox[V15_MBOX_MAILBOX_VALID] = V15_MAILBOX_VALID;
    __DSB();
}

__attribute__((noinline))
static void v15_publish_failure(uint32_t phase, uint32_t reason, uint32_t qread, uint32_t status)
{
    pmu_completion_visibility_v15_mailbox[V15_MBOX_CONVERGENCE_FINAL_QREAD] = V15_U32_INVALID;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_CONVERGENCE_FINAL_STATUS] = V15_U32_INVALID;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_PHASE] = phase;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_REASON] = reason;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_QREAD] = qread;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_STATUS] = status;
    v15_mailbox_publish();
}

__attribute__((noinline))
static void v15_publish_cleanup_failure(uint32_t qread, uint32_t status)
{
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_PHASE] = V15_PHASE_CLEANUP;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_REASON] = V15_REASON_CLEANUP_INVARIANT;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_QREAD] = qread;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_STATUS] = status;
    v15_mailbox_publish();
}

__attribute__((noinline))
static void v15_publish_success(void)
{
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_PHASE] = V15_PHASE_NONE;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_REASON] = V15_REASON_NONE;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_QREAD] = V15_U32_INVALID;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FAILURE_STATUS] = V15_U32_INVALID;
    v15_mailbox_publish();
}

__attribute__((noinline))
static void v15_publish_primary(const struct v15_observation_t *obs, uint32_t qsize_expected)
{
    pmu_completion_visibility_v15_mailbox[V15_MBOX_PRIMARY_RESULT] = obs->result;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_PRIMARY_ITERATIONS] = obs->iterations;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_T_FIRST_OBSERVATION] = obs->t_first;
    if (obs->result != V15_PRIMARY_OBSERVED) {
        pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_QREAD] = V15_U32_INVALID;
        pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_STATUS] = V15_U32_INVALID;
        pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_Q_DONE] = V15_U32_INVALID;
        pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_CMD_END_REACHED] = V15_U32_INVALID;
        pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_IRQ_RAISED] = V15_U32_INVALID;
        pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_STATE] = V15_U32_INVALID;
        return;
    }
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_QREAD] = obs->qread;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_STATUS] = obs->status;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_Q_DONE] = (obs->qread == qsize_expected) ? 1U : 0U;
    if (obs->status == V15_U32_INVALID) {
        pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_CMD_END_REACHED] = V15_U32_INVALID;
        pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_IRQ_RAISED] = V15_U32_INVALID;
        pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_STATE] = V15_U32_INVALID;
        return;
    }
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_CMD_END_REACHED] = ((obs->status & V15_STATUS_CMD_END) != 0U) ? 1U : 0U;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_IRQ_RAISED] = ((obs->status & V15_STATUS_IRQ_RAISED) != 0U) ? 1U : 0U;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_FIRST_STATE] = (obs->status & V15_STATUS_STATE);
}

__attribute__((noinline))
static void v15_primary_s5(uint32_t qsize_expected, struct v15_observation_t *obs)
{
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t status = 0U;

    (void)qsize_expected;

    for (uint32_t i = 1U; i <= V15_ITERATION_BOUND; ++i) {
        status = *status_reg;
        if ((status & V15_STATUS_CMD_END) != 0U) {
            obs->t_first = DWT->CYCCNT;
            obs->result = V15_PRIMARY_OBSERVED;
            obs->iterations = i;
            obs->qread = V15_U32_INVALID;
            obs->status = status;
            return;
        }
    }

    obs->t_first = V15_U32_INVALID;
    obs->iterations = 0U;
    obs->qread = V15_U32_INVALID;
    obs->status = status;
    if ((status & V15_STATUS_RESET) != 0U) {
        obs->result = V15_PRIMARY_RESET;
        return;
    }
    if ((status & V15_STATUS_FAULT_MASK) != 0U) {
        obs->result = V15_PRIMARY_FAULT;
        return;
    }
    obs->result = V15_PRIMARY_TIMEOUT;
}

__attribute__((noinline))
static void v15_converge(uint32_t qsize_expected, struct v15_observation_t *obs)
{
    volatile uint32_t *const qread_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_QREAD);
    volatile uint32_t *const status_reg =
        (volatile uint32_t *)(uintptr_t)(U85_BASE_ADDRESS + NPU_REG_STATUS);
    uint32_t qread = 0U;
    uint32_t status = 0U;
    uint32_t result = V15_CONVERGENCE_TIMEOUT;
    uint32_t iterations = 0U;

    for (uint32_t i = 1U; i <= V15_ITERATION_BOUND; ++i) {
        qread = *qread_reg;
        status = *status_reg;
        if ((status & V15_STATUS_RESET) != 0U) {
            result = V15_CONVERGENCE_RESET;
            break;
        }
        if ((status & V15_STATUS_FAULT_MASK) != 0U) {
            result = V15_CONVERGENCE_FAULT;
            break;
        }
        if ((qread == qsize_expected) &&
            ((status & V15_STATUS_CMD_END) != 0U) &&
            ((status & V15_STATUS_IRQ_RAISED) != 0U) &&
            ((status & V15_STATUS_STATE) == 0U)) {
            result = V15_CONVERGENCE_SUCCESS;
            iterations = i;
            break;
        }
    }

    obs->t_first = V15_U32_INVALID;
    obs->result = result;
    obs->iterations = iterations;
    obs->qread = qread;
    obs->status = status;
}

static int test_commands( const u85_eTest eTest,
		                  const uint32_t u32CmdQueueSize,
		                  struct u85_warp_data_t *pu85_warp_data_st)
{
	int ret_code;
    int read_val;
    uint32_t qsize_expected;
    uint32_t pre_submit_status;
    struct v15_observation_t primary;
    struct v15_observation_t converged;

	/* Init locals */
	ret_code =0;
	read_val =0;
    qsize_expected = 0U;
    pre_submit_status = 0U;

    printf("Always ask for CLK and PWR on Q interfaces\n");
    //Writing a 0 Bit[2] enables CLKQ, and Bit[3] Enables PWRQ
    write_reg(NPU_REG_CMD, 0x00000000);

	if(eTest==eU85_TEST0)
	{
		  read_val = read_reg(NPU_REG_PROT);
		  printf("PORPL is connected to: %0x, PORSL is connected to: %0x\n", read_val & 0x1, (read_val & 0x2) >> 1);

		  if(read_reg(NPU_REG_ID) == NPU_ID) {
		  } else{
			ret_code = 1;
		  }

		  if(read_reg(NPU_REG_CONFIG) == NPU_CFG_REG) {
		  } else {
			ret_code = 2;
		  }
		  write_reg(NPU_REG_QBASE_LSB, 0xAAAAAAAA);
		  if(read_reg(NPU_REG_QBASE_LSB) == 0xAAAAAAAA) {
		  } else {
			ret_code = 3;
		  }
		  // Write and read back values from a 32 bit RW register
		  // to toggle all pins
		  write_reg(NPU_REG_QBASE_LSB, 0x55555555);
		  if(read_reg(NPU_REG_QBASE_LSB) == 0x55555555) {
		  } else {
			ret_code = 4;
		  }
	}
	else
	{
#if(TEST_PROT==1)
	    // Program security and privilege levels
	    // The value programmed into NPU_REG_RESET will be affect
	    // the protection bits used by the bus transfers
	    // Bit[0] : Privilege level to apply after reset
	    // Bit[1] : Security  level to apply after reset
	    // Refer to the programmers manual for more details
	    printf("Enabling PROT signals testing\n");
	    write_reg(NPU_REG_RESET, 0x3);
	    wait_for_reset();
	    read_val = read_reg(NPU_REG_PROT);
	    printf("PORPL is : %0x, PORSL is : %0x\n", read_val & 0x1, (read_val & 0x2) >> 1);
#endif

	  // Product supports 256 Byte bursts
	  // Setup AXI_SRAM and AXI_EXT registers
	  // Max Outstanding reads_m1 = 31
	  // Max Outstanding write_m1 = 15
	  // Setup longer (256B) length bursts
	  write_reg(NPU_REG_AXI_SRAM, 0x00021F3F);
	  write_reg(NPU_REG_AXI_EXT , 0x00021F3F);
	  // Setup CAP regs to be same as AXI regs
	  write_reg(NPU_REG_CFG_SRAM_CAP , 0x00021F3F);
	  write_reg(NPU_REG_CFG_EXT_CAP  , 0x00021F3F);
	  // Setup memory attributes
	  // mem_domain = non_shareable
	  // axi_port   = SRAM port
	  // memtype    = Device non bufferable
	  write_reg(NPU_REG_MEM_ATTR0, 0x00000000);
	  write_reg(NPU_REG_MEM_ATTR1, 0x00000000);
	  write_reg(NPU_REG_MEM_ATTR2, 0x00000000);
	  write_reg(NPU_REG_MEM_ATTR3, 0x00000000);

#if(TOGGLE_AXCACHE==1)
	    // Setup memtype to Bufferable, cacheable, read allocate, write allocate
	    write_reg(NPU_REG_MEM_ATTR0, read_reg(NPU_REG_MEM_ATTR0) | 0x000000B0);
	    write_reg(NPU_REG_MEM_ATTR1, read_reg(NPU_REG_MEM_ATTR1) | 0x000000B0);
	    write_reg(NPU_REG_MEM_ATTR2, read_reg(NPU_REG_MEM_ATTR2) | 0x000000B0);
	    write_reg(NPU_REG_MEM_ATTR3, read_reg(NPU_REG_MEM_ATTR3) | 0x000000B0);
#endif
#if(TOGGLE_AXDOMAIN==1)
	    // Setup mem_domain to system
	    write_reg(NPU_REG_MEM_ATTR0, read_reg(NPU_REG_MEM_ATTR0) | 0x00000003);
	    write_reg(NPU_REG_MEM_ATTR1, read_reg(NPU_REG_MEM_ATTR1) | 0x00000003);
	    write_reg(NPU_REG_MEM_ATTR2, read_reg(NPU_REG_MEM_ATTR2) | 0x00000003);
	    write_reg(NPU_REG_MEM_ATTR3, read_reg(NPU_REG_MEM_ATTR3) | 0x00000003);
#endif

#if(USE_AXI_EXT==1)
	    // Setup mem_domain to system
	    printf("Enabling AXI EXT port testing\n");
	    write_reg(NPU_REG_MEM_ATTR0, read_reg(NPU_REG_MEM_ATTR0) | 0x00000004);
	    write_reg(NPU_REG_MEM_ATTR1, read_reg(NPU_REG_MEM_ATTR1) | 0x00000004);
	    write_reg(NPU_REG_MEM_ATTR2, read_reg(NPU_REG_MEM_ATTR2) | 0x00000004);
	    write_reg(NPU_REG_MEM_ATTR3, read_reg(NPU_REG_MEM_ATTR3) | 0x00000004);
#endif

	  // BASEP0 is configured to point to Weight stream
	  // This is configured by the CMD0_NPU_SET_WEIGHT_REGION command
	  // that chooses region 0 for weights
	  write_reg(NPU_REG_BASEP0_LSB, (uint32_t)pu85_warp_data_st->weights);
	  write_reg(NPU_REG_BASEP0_MSB, 0x00000000);
	  // BASEP1 is configured to point to scratch data section
	  // The app.scatter file should match this
	  write_reg(NPU_REG_BASEP1_LSB, (uint32_t)pu85_warp_data_st->scratch_buffer);
	  write_reg(NPU_REG_BASEP1_MSB, 0x00000000);
	  // BASEP2 is configured to point to IFM stream
	  // This is configured by the CMD0_NPU_SET_IFM_REGION command
	  // that chooses region 2 for ifm data
	  write_reg(NPU_REG_BASEP2_LSB, (uint32_t)pu85_warp_data_st->in_data_0);
	  write_reg(NPU_REG_BASEP2_MSB, 0x00000000);
	  // BASEP3 is configured to point to OFM stream
	  // This is configured by the CMD0_NPU_SET_OFM_REGION command
	  // that chooses region 3 for ofm data
	  write_reg(NPU_REG_BASEP3_LSB, (uint32_t)pu85_warp_data_st->out_data_0);
	  write_reg(NPU_REG_BASEP3_MSB, 0x00000000);
	  // QBASE_LSB and QBASE_MSB are configured to point to command stream
	  // They should match with the setting in the scatter file
	  write_reg(NPU_REG_QBASE_LSB, (uint32_t)pu85_warp_data_st->cmd_st);
	  write_reg(NPU_REG_QBASE_MSB, 0x00000000);
	  //Size of command stream
	  write_reg(NPU_REG_QSIZE, u32CmdQueueSize);
	  write_reg(NPU_REG_QCONFIG, 0x00000000);
	  // Region config sets up which axi interface to use for what region
	  // bits[1:0] are for region 0
	  // bits[3:2] are for region 1 and so on
	  // Use MEM_ATTR0 for all regions
	  write_reg(NPU_REG_REGIONCFG, 0x00000000);


	  printf("Updating POWER_CTRL register with MAC_RAMP_VAR=%d \n", MAC_RAMP_VAR);

	  write_reg(NPU_REG_POWER_CTRL, MAC_RAMP_VAR);


	  qsize_expected = read_reg(NPU_REG_QSIZE);
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_QSIZE_EXPECTED] = qsize_expected;
	  pre_submit_status = read_reg(NPU_REG_STATUS);
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_PRE_SUBMIT_STATUS] = pre_submit_status;
	  if (qsize_expected != V15_QSIZE_EXPECTED) {
	    v15_publish_failure(V15_PHASE_PRE_SUBMIT, V15_REASON_QSIZE_MISMATCH, V15_U32_INVALID, pre_submit_status);
	    return V15_RET_PRE_SUBMIT_FAILURE;
	  }
	  if ((pre_submit_status & V15_STATUS_STATE) != 0U) {
	    v15_publish_failure(V15_PHASE_PRE_SUBMIT, V15_REASON_STATE_RUNNING, V15_U32_INVALID, pre_submit_status);
	    return V15_RET_PRE_SUBMIT_FAILURE;
	  }
	  if ((pre_submit_status & V15_STATUS_RESET) != 0U) {
	    v15_publish_failure(V15_PHASE_PRE_SUBMIT, V15_REASON_RESET_IN_PROGRESS, V15_U32_INVALID, pre_submit_status);
	    return V15_RET_RESET_IN_PROGRESS;
	  }
	  if ((pre_submit_status & V15_STATUS_FAULT_MASK) != 0U) {
	    v15_publish_failure(V15_PHASE_PRE_SUBMIT, V15_REASON_HARDWARE_FAULT, V15_U32_INVALID, pre_submit_status);
	    return V15_RET_HARDWARE_FAULT;
	  }
	  if ((pre_submit_status & V15_STATUS_IRQ_RAISED) != 0U) {
	    v15_publish_failure(V15_PHASE_PRE_SUBMIT, V15_REASON_STALE_IRQ, V15_U32_INVALID, pre_submit_status);
	    return V15_RET_PRE_SUBMIT_FAILURE;
	  }
	  if ((pre_submit_status & V15_STATUS_CMD_END) != 0U) {
	    v15_publish_failure(V15_PHASE_PRE_SUBMIT, V15_REASON_STALE_CMD_END, V15_U32_INVALID, pre_submit_status);
	    return V15_RET_PRE_SUBMIT_FAILURE;
	  }
	  //Start NPU
	  read_val = read_reg(NPU_REG_CMD);
	  write_reg(NPU_REG_CMD, read_val | 0x00000001);
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_T_SUBMIT_AFTER_CMD] = DWT->CYCCNT;
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_T_PRIMARY_ENTRY] = DWT->CYCCNT;
	  v15_primary_s5(qsize_expected, &primary);
	  v15_publish_primary(&primary, qsize_expected);
	  if (primary.result != V15_PRIMARY_OBSERVED) {
	    if (primary.result == V15_PRIMARY_RESET) {
	      v15_publish_failure(V15_PHASE_PRIMARY, V15_REASON_RESET_IN_PROGRESS, primary.qread, primary.status);
	      return V15_RET_RESET_IN_PROGRESS;
	    }
	    if (primary.result == V15_PRIMARY_FAULT) {
	      v15_publish_failure(V15_PHASE_PRIMARY, V15_REASON_HARDWARE_FAULT, primary.qread, primary.status);
	      return V15_RET_HARDWARE_FAULT;
	    }
	    v15_publish_failure(V15_PHASE_PRIMARY, V15_REASON_PRIMARY_TIMEOUT, primary.qread, primary.status);
	    return V15_RET_PRIMARY_TIMEOUT;
	  }
	  v15_converge(qsize_expected, &converged);
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_CONVERGENCE_RESULT] = converged.result;
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_CONVERGENCE_ITERATIONS] = converged.iterations;
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_CONVERGENCE_TIMEOUT] =
	      (converged.result == V15_CONVERGENCE_TIMEOUT) ? 1U : 0U;
	  if (converged.result != V15_CONVERGENCE_SUCCESS) {
	    if (converged.result == V15_CONVERGENCE_RESET) {
	      v15_publish_failure(V15_PHASE_CONVERGENCE, V15_REASON_RESET_IN_PROGRESS, converged.qread, converged.status);
	      return V15_RET_RESET_IN_PROGRESS;
	    }
	    if (converged.result == V15_CONVERGENCE_FAULT) {
	      v15_publish_failure(V15_PHASE_CONVERGENCE, V15_REASON_HARDWARE_FAULT, converged.qread, converged.status);
	      return V15_RET_HARDWARE_FAULT;
	    }
	    v15_publish_failure(V15_PHASE_CONVERGENCE, V15_REASON_CONVERGENCE_TIMEOUT, converged.qread, converged.status);
	    return V15_RET_CONVERGENCE_TIMEOUT;
	  }
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_CONVERGENCE_FINAL_QREAD] = converged.qread;
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_CONVERGENCE_FINAL_STATUS] = converged.status;
	  irq_history_mask = converged.status >> 16;
	  write_reg(NPU_REG_CMD, 0x00000002);
	  read_val = read_reg(NPU_REG_QREAD);
	  write_reg(NPU_REG_CMD, 0x00000002);
	  if(read_val == u32CmdQueueSize) {
	    printf("Read match at address: NPU_REG_QREAD, Expected Read Value: 0x%x \n",u32CmdQueueSize);
	  }
	  else {
	    printf("ERROR: Read mismatch at address: NPU_REG_QREAD, Expected Read Value: 0x%x, Read Value : 0x%x\n",u32CmdQueueSize, read_val);
	    ret_code = 1;
	  }
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_NVIC_PENDING_BEFORE_FINAL_CLEAR] = NVIC_GetPendingIRQ(NPU0_IRQn);
	  NVIC_ClearPendingIRQ(NPU0_IRQn);
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_NVIC_PENDING_AFTER_FINAL_CLEAR] = NVIC_GetPendingIRQ(NPU0_IRQn);
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_NVIC_ACTIVE_AFTER_CLEANUP] = NVIC_GetActive(NPU0_IRQn);
	  pmu_completion_visibility_v15_mailbox[V15_MBOX_IRQ_TRIGGERED_AFTER_CLEANUP] = irq_triggered ? 1U : 0U;
	  //Stop NPU
	  write_reg(NPU_REG_CMD, 0x00000000);
	  // Enable clock and power Q interfaces to ask for shutdown
#if(TEST_CPM==1)
	    /* V12_HPRINTF_SEAM */
	    printf("Testing CPM signals\n");
	    //Enable Program CLKQ and PWRQ interfaces
	    //Bit[2] enables CLKQ, and Bit[3] Enables PWRQ
	    write_reg(NPU_REG_CMD, 0x0000000C);
#endif
	  if (ret_code != 0) {
	    v15_publish_cleanup_failure((uint32_t)read_val, converged.status);
	    ret_code = V15_RET_CLEANUP_INVARIANT;
	  }
	  else {
	    v15_publish_success();
	    ret_code = V15_RET_SUCCESS;
	  }
  }

  return ret_code;
}

/*****************************************************************************
 *                         Global function defns
 * **************************************************************************/
int test_u85( const u85_eTest eTest,
              const uint32_t u32ExpectedIRQMask,
              const uint32_t u32OutputSize,
              const uint32_t u32CmdQueueSize,
              struct u85_warp_data_t *pu85_warp_data_st )
{
    int ret_code = 0;

    //Set up the IRQ handler of the host
    NVIC_SetVector(NPU0_IRQn, (uint32_t)&u85_irq_handler);
    irq_triggered = false;
    NVIC_DisableIRQ(NPU0_IRQn);
    NVIC_ClearPendingIRQ(NPU0_IRQn);

    pmu_completion_visibility_v15_mailbox[V15_MBOX_VARIANT_ID] = V15_VARIANT_ID;
    pmu_completion_visibility_v15_mailbox[V15_MBOX_INSTALLED_VECTOR] = NVIC_GetVector(NPU0_IRQn);
    pmu_completion_visibility_v15_mailbox[V15_MBOX_NVIC_ENABLED_BEFORE_SUBMIT] = NVIC_GetEnableIRQ(NPU0_IRQn);
    pmu_completion_visibility_v15_mailbox[V15_MBOX_NVIC_PENDING_AFTER_INITIAL_CLEAR] = NVIC_GetPendingIRQ(NPU0_IRQn);
    pmu_completion_visibility_v15_mailbox[V15_MBOX_NVIC_ACTIVE_BEFORE_SUBMIT] = NVIC_GetActive(NPU0_IRQn);
    pmu_completion_visibility_v15_mailbox[V15_MBOX_IRQ_TRIGGERED_BEFORE_SUBMIT] = irq_triggered ? 1U : 0U;

    if ((pmu_completion_visibility_v15_mailbox[V15_MBOX_INSTALLED_VECTOR] != (uint32_t)&u85_irq_handler) ||
        (pmu_completion_visibility_v15_mailbox[V15_MBOX_NVIC_ENABLED_BEFORE_SUBMIT] != 0U) ||
        (pmu_completion_visibility_v15_mailbox[V15_MBOX_NVIC_PENDING_AFTER_INITIAL_CLEAR] != 0U) ||
        (pmu_completion_visibility_v15_mailbox[V15_MBOX_NVIC_ACTIVE_BEFORE_SUBMIT] != 0U) ||
        (pmu_completion_visibility_v15_mailbox[V15_MBOX_IRQ_TRIGGERED_BEFORE_SUBMIT] != 0U)) {
        v15_publish_failure(V15_PHASE_PRE_PROGRAM, V15_REASON_STATE_RUNNING, V15_U32_INVALID, V15_U32_INVALID);
        return V15_RET_PRE_PROGRAM_FAILURE;
    }

    {
        uint32_t pre_program_status = read_reg(NPU_REG_STATUS);

        pmu_completion_visibility_v15_mailbox[V15_MBOX_PRE_PROGRAM_STATUS] = pre_program_status;
        if ((pre_program_status & V15_STATUS_STATE) != 0U) {
            v15_publish_failure(V15_PHASE_PRE_PROGRAM, V15_REASON_STATE_RUNNING, V15_U32_INVALID, pre_program_status);
            return V15_RET_PRE_PROGRAM_FAILURE;
        }
        if ((pre_program_status & V15_STATUS_RESET) != 0U) {
            v15_publish_failure(V15_PHASE_PRE_PROGRAM, V15_REASON_RESET_IN_PROGRESS, V15_U32_INVALID, pre_program_status);
            return V15_RET_RESET_IN_PROGRESS;
        }
        if ((pre_program_status & V15_STATUS_FAULT_MASK) != 0U) {
            v15_publish_failure(V15_PHASE_PRE_PROGRAM, V15_REASON_HARDWARE_FAULT, V15_U32_INVALID, pre_program_status);
            return V15_RET_HARDWARE_FAULT;
        }
    }

    //Wait for reset to finish
    wait_for_reset();
    //configure NPU

    ret_code = test_commands(eTest,u32CmdQueueSize,pu85_warp_data_st);

#if(VERIFY_OUTPUT==1)
        // Outputs
        int result;
        result = memcmp(
       		pu85_warp_data_st->out_data_0,
			pu85_warp_data_st->out_ver_data_0,
			u32OutputSize);
        if (0 == result) {
        } else {
            ret_code = 2;
            for ( uint32_t i= 0; i<u32OutputSize; i++){
              if ( pu85_warp_data_st->out_data_0[i] != pu85_warp_data_st->out_ver_data_0[i]) {
            	  printf("actual @i=%d actual is  0x%02x expected is 0x%02x \n", i, pu85_warp_data_st->out_data_0[i], pu85_warp_data_st->out_ver_data_0[i]);
            	  break;
              }
            }
        }
#endif

    if(eTest != eU85_TEST0)
    {        // Check mask when receiving IRQ
        if(irq_history_mask == u32ExpectedIRQMask) {
        } else {
        	printf("irq_history_mask is not equal as EXPECTED_IRQ_MASK\n");
            ret_code = 3;
        }
    }

    if(irq_never_triggered != false) {
    	ret_code++;
    }

    return ret_code;
}
