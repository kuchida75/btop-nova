/* Test-only sysfs directory redirection; never installed with btop. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdlib.h>
#include <string.h>
char *realpath(const char *path, char *resolved) {
    char *(*original)(const char *, char *) = dlsym(RTLD_NEXT, "realpath");
    const char *root = getenv("NOVA_TEST_POWER_FILES");
    return original(root && !strcmp(path, "/sys/class/powercap") ? root : path, resolved);
}
