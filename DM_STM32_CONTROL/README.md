stm32 control


Linux Makefile dev


```openocd.cfg
source [find interface/stlink-dap.cfg]
transport select dapdirect_swd

set WORKAREASIZE 0x3000
set CHIPNAME STM32H723ZG
set BOARDNAME NUCLEO-H723ZG

source [find target/stm32h7x.cfg]

# Use connect_assert_srst here to be able to program
# even when core is in sleep mode
reset_config srst_only srst_nogate connect_assert_srst

$_CHIPNAME.cpu0 configure -event gdb-attach {
        echo "Debugger attaching: halting execution"
        gdb_breakpoint_override hard
}

$_CHIPNAME.cpu0 configure -event gdb-detach {
        echo "Debugger detaching: resuming execution"
        resume
}

# Due to the use of connect_assert_srst, running gdb requires
# to reset halt just after openocd init.
rename init old_init
proc init {} {
        old_init
        reset halt
}
```

```bash
openocd -f interface/stlink.cfg -f target/stm32h7x.cfg

gdb-multiarch build/CtrBoard.elf

sudo apt-get install gdb-multiarch

target extended-remote 3333

monitor reset_config srst_only connect_assert_srst


/opt/st/stm32cubeide_1.18.1/plugins/com.st.stm32cube.ide.mcu.externaltools.stlink-gdb-server.linux64_2.2.100.202501151542/tools/bin/ST-LINK_gdbserver -cp /opt/st/stm32cubeide_1.18.1/plugins/com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.linux64_2.2.100.202412061334/tools/bin -d -p 3333
```


