OUTPUT_FORMAT("elf32-littlearm", "elf32-littlearm", "elf32-littlearm")
OUTPUT_ARCH(arm)
ENTRY(Reset_Handler)
MEMORY
{
  ROM (rx) : ORIGIN = ( (0x11000000) ), LENGTH = ( (0x00020000) )
  SRAM (rwx) : ORIGIN = ( (0x31000000) ), LENGTH = ( (0x00400000) )
  DDR (rw) : ORIGIN = 0x90000000, LENGTH = 0x00020000
  NOINIT (rw) : ORIGIN = 0x90020000, LENGTH = 0x00100000
}
__HEAP_SIZE = (0x00004000);
__STACK_SIZE = (0x00020000);
SECTIONS
{
    .vectors_rom :
    {
        KEEP(*(.vectors))
        KEEP(*(RESET))
        KEEP(*(InRoot$$Sections))
    } > ROM
    .ddr :
    {
        KEEP(*(sec_command_stream))
        KEEP(*(sec_input_data))
        KEEP(*(sec_weight_data))
    } > DDR =0xFFFFFFFF
    .sec_noinit (NOLOAD) :
    {
        KEEP(*(.bss.sec_scratch_buffer))
        KEEP(*(.bss.sec_output_data))
    } > NOINIT
    .text :
    {
        *(.text*)
        KEEP(*(.init))
        KEEP(*(.fini))
        *crtbegin.o(.ctors)
        *crtbegin?.o(.ctors)
        *(EXCLUDE_FILE(*crtend?.o *crtend.o) .ctors)
        *(SORT(.ctors.*))
        *(.ctors)
        *crtbegin.o(.dtors)
        *crtbegin?.o(.dtors)
        *(EXCLUDE_FILE(*crtend?.o *crtend.o) .dtors)
        *(SORT(.dtors.*))
        *(.dtors)
        *(.rodata*)
        KEEP(*(.eh_frame*))
    } > SRAM
    .ARM.extab :
    {
        *(.ARM.extab* .gnu.linkonce.armextab.*)
    } > SRAM
    __exidx_start = .;
    .ARM.exidx :
    {
        *(.ARM.exidx* .gnu.linkonce.armexidx.*)
    } > SRAM
    __exidx_end = .;
    .preinit_array :
    {
        PROVIDE_HIDDEN(__preinit_array_start = .);
        KEEP(*(.preinit_array))
        PROVIDE_HIDDEN(__preinit_array_end = .);
    } > SRAM
    .init_array :
    {
        PROVIDE_HIDDEN(__init_array_start = .);
        KEEP(*(SORT(.init_array.*)))
        KEEP(*(.init_array))
        PROVIDE_HIDDEN(__init_array_end = .);
    } > SRAM
    .fini_array :
    {
        PROVIDE_HIDDEN(__fini_array_start = .);
        KEEP(*(SORT(.fini_array.*)))
        KEEP(*(.fini_array))
        PROVIDE_HIDDEN(__fini_array_end = .);
    } > SRAM
    .copy.table : ALIGN(4)
    {
        __copy_table_start__ = .;
        __copy_table_end__ = .;
    } > SRAM
    .zero.table : ALIGN(4)
    {
        __zero_table_start__ = .;
        LONG(__bss_start__)
        LONG((__bss_end__ - __bss_start__) / 4)
        __zero_table_end__ = .;
    } > SRAM
    __ro_limit = .;
    .ro_padding (NOLOAD) :
    {
        . = . + 0x1000;
    } > SRAM
    .vectors_ram : ALIGN(512)
    {
        KEEP(*(RESET_RAM))
    } > SRAM
    .data :
    {
        . = ALIGN(4);
        __data_start__ = .;
        *(vtable)
        *(.data*)
        . = ALIGN(4);
        __data_end__ = .;
    } > SRAM
    .bss (NOLOAD) :
    {
        . = ALIGN(4);
        __bss_start__ = .;
        PROVIDE(__bss_start = .);
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        __bss_end__ = .;
        PROVIDE(__bss_end = .);
    } > SRAM
    .heap (NOLOAD) : ALIGN(8)
    {
        __end__ = .;
        PROVIDE(end = .);
        PROVIDE(_end = .);
        __HeapBase = .;
        . = . + __HEAP_SIZE;
        __HeapLimit = .;
        __heap_limit = .;
    } > SRAM
    .stack (NOLOAD) : ALIGN(32)
    {
        . = . + __STACK_SIZE - 0x8;
    } > SRAM
    .stackseal (NOLOAD) :
    {
        . = . + 0x8;
    } > SRAM
    __StackLimit = ADDR(.stack);
    __StackTop = ADDR(.stack) + SIZEOF(.stack);
    PROVIDE(__stack = __StackTop);
    __INITIAL_SP = __StackTop;
    __STACK_LIMIT = __StackLimit;
    __STACK_SEAL = ADDR(.stackseal);
    __sram_watermark = .;
    .ARM.attributes 0 : { *(.ARM.attributes) }
    /DISCARD/ :
    {
        *(.comment)
        *(.note.*)
    }
}
ASSERT(ADDR(.vectors_rom) + SIZEOF(.vectors_rom) <= ( (0x11000000) ) + ( (0x00020000) ),
       "LR_ROM overflow: vector table does not fit in the 128 KB BOOT ROM")
ASSERT(__sram_watermark <= ( (0x31000000) ) + ( (0x00400000) ),
       "LR_RAM overflow: image does not fit in the 4 MB secure internal SRAM")
ASSERT(SIZEOF(.ddr) <= 0x00020000,
       "LR_DDR overflow: NPU streams exceed 128 KB")
ASSERT(SIZEOF(.sec_noinit) <= 0x00100000,
       "LR_NoInit overflow: NPU scratch/output exceed 1 MB")
