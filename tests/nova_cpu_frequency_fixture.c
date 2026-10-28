/* Test-only read redirection; never installed or used by the production build. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static FILE *fixture(const char *symbol, const char *path, const char *mode) {
    FILE *(*original)(const char *, const char *) = dlsym(RTLD_NEXT, symbol);
    const char *root = getenv("NOVA_TEST_CPU_FILES");
    const char *prefix = "/sys/devices/system/cpu/";
    char mapped[PATH_MAX];
    if (root && !strcmp(mode, "r")) {
        const char *relative = !strcmp(path, "/proc/cpuinfo") ? "cpuinfo"
            : !strncmp(path, prefix, strlen(prefix)) ? path + strlen(prefix) : NULL;
        if (relative) {
            int length = snprintf(mapped, sizeof(mapped), "%s/%s", root, relative);
            if (length > 0 && length < (int)sizeof(mapped)) path = mapped;
        }
    }
    return original(path, mode);
}
FILE *fopen(const char *path, const char *mode) { return fixture("fopen", path, mode); }
FILE *fopen64(const char *path, const char *mode) { return fixture("fopen64", path, mode); }
