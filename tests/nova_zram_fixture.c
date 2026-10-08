/* Test-only read shim. Synthetic zram counters are confined to the test
 * process; no host swap, sysfs file or production collector is modified. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

static FILE *read_fixture(const char *symbol, const char *path, const char *mode) {
    FILE *(*original)(const char *, const char *) = dlsym(RTLD_NEXT, symbol);
    const char *root = getenv("NOVA_TEST_ZRAM_FILES");
    const char *file = !strcmp(path, "/proc/swaps") ? "swaps"
        : !strcmp(path, "/sys/block/zram0/mm_stat") ? "mm_stat" : NULL;
    char mapped[PATH_MAX];
    if (root && file && !strcmp(mode, "r")) {
        int length = snprintf(mapped, sizeof(mapped), "%s/%s", root, file);
        if (length > 0 && length < (int)sizeof(mapped)) path = mapped;
    }
    return original(path, mode);
}
FILE *fopen(const char *path, const char *mode) { return read_fixture("fopen", path, mode); }
FILE *fopen64(const char *path, const char *mode) { return read_fixture("fopen64", path, mode); }
