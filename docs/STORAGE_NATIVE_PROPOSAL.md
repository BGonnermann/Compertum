# Proposed native storage reader

14 October2026. Owner approved the native scanner and three additional review rounds4–6. The used Python rounds1–3 and all their failures remain in the record. No compiled reader has been written, built, installed or admitted.

The Python repair passes32 affected native source tests and implementation review3. It still cannot scan the full master folder within five seconds on the watchdog's one CPU. Four, two and one Python readers all exceeded five seconds in a separately identified offline cost experiment. The category, memory, CPU and time limits remain fixed. A preservation preflight for52 passed disposable roots measured12,738,069 compressed bytes, exceeding the five-MiB archive allowance; it wrote no backup and removed nothing.

Proposed next approach: retain Python accounting and link validation, and combine the existing Win32 directory-open checks and native directory reads into a small C library. GCC16.1.0 for x86_64 UCRT is already installed. No compiler installation, spending, account permission or administrator action is proposed.

The native library would expose bounded directory open/read/close operations. It would use the existing access/share/flag checks, native AllocationSize,64KiB batches and strict status/error handling. Python would continue to merge every entry, preserve inherited categories, resolve reparses while the directory remains locked, run caller-thread volume checks and enforce total scan elapsed time including closure. A single native call could combine operations that currently cross Python's native boundary separately. This is a performance hypothesis, not verified timing.

Freeze the C source, compiler executable/version, compile command, exported ABI, resulting library hash and source/package placement before qualification. Build offline in a checked scratch namespace. Reject unknown library bytes or incompatible platforms. Extend source/package manifests and build checks to cover the native payload explicitly. Avoid a runtime compiler, external service or downloaded binary.

Acceptance must include exact inventories and allocation charges, all existing scanner/watchdog cases, malformed rows/statuses, link locking, callback/error/close behavior, dependency-unchanged offline build/install and real full-master scans within five seconds in the actual one-CPU128MiB job. Carry Python repair rounds1–3 and their failures forward. The approved extra review budget starts at round4; never rename the work to hide the used rounds.

Native row layout reference: [Microsoft FILE_FULL_DIR_INFORMATION](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_full_dir_information). Existing64KiB batches and eight-byte row alignment stay explicit.
