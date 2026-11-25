/* Fault recovery and reporting (pqb_rp_fault.c). */
#ifndef PQB_RP_FAULT_H
#define PQB_RP_FAULT_H

#define PQB_WDT_MS 5000

/* Name of the operation running now, recorded with a fault */
extern volatile const char* pqb_current_op;

/* At boot, before the scheduler: keep any fault record and start the watchdog */
void pqb_fault_boot(void);
/* Prints the fault record found at boot, if any, as a "#fault" line */
void pqb_fault_print(void);
void pqb_fault_clear(void);
int pqb_fault_watchdog_reboot(void);

#endif
