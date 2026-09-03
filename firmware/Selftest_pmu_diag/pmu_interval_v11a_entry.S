.syntax unified
.thumb

.section .text.v11a_u85_irq_entry_veneer, "ax", %progbits
.align 2
.global v11a_u85_irq_entry_veneer
.type v11a_u85_irq_entry_veneer, %function
.thumb_func
v11a_u85_irq_entry_veneer:
    ldr r0, =0xE0001004
    ldr r1, [r0]
    ldr r0, =pmu_interval_v11a_t_vector_probe
    str r1, [r0]
    b.w u85_irq_handler
.size v11a_u85_irq_entry_veneer, . - v11a_u85_irq_entry_veneer
