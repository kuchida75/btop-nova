/* Test-only NVML provider. Loaded only by a test process via LD_LIBRARY_PATH;
 * it is never installed and does not access real GPUs or change their driver. */
#include <stdio.h>
#include <stdlib.h>

typedef struct { unsigned gpu, memory; } utilization;
typedef struct { unsigned long long total, free, used; } memory_info;
static unsigned samples;
static unsigned wave(void) { unsigned phase = samples % 48; return phase <= 24 ? phase : 48-phase; }
const char *nvmlErrorString(int code) { (void)code; return "fixture unsupported"; }
int nvmlInit(void) { return 0; }
int nvmlShutdown(void) { return 0; }
int nvmlDeviceGetCount(unsigned *count) { *count = 1; return 0; }
int nvmlDeviceGetHandleByIndex(unsigned index, void **device) { (void)index; *device = (void *)1; return 0; }
int nvmlDeviceGetName(void *device, char *name, unsigned size) { (void)device; snprintf(name, size, "Nova fixture GPU"); return 0; }
int nvmlDeviceGetPowerManagementLimit(void *device, unsigned *value) { (void)device; *value = 300000; return 0; }
int nvmlDeviceGetTemperatureThreshold(void *device, int kind, unsigned *value) { (void)device; (void)kind; *value = 100; return 0; }
int nvmlDeviceGetUtilizationRates(void *device, utilization *value) {
    (void)device;
    if (getenv("NOVA_FIXTURE_NO_LOAD")) return 3;
    ++samples;
    value->gpu = getenv("NOVA_FIXTURE_DOT_WAVE") ? 4 + wave() : 20 + (samples % 3) * 5;
    value->memory = 7; /* memory-controller activity is not allocated VRAM */
    return 0;
}
int nvmlDeviceGetClockInfo(void *device, int kind, unsigned *value) {
    (void)device;
    *value = getenv("NOVA_FIXTURE_DOT_WAVE") ? (kind == 0 ? 450 + wave()*30 : 405 + wave()*20) : (kind == 0 ? 900 : 405);
    return 0;
}
int nvmlDeviceGetPowerUsage(void *device, unsigned *value) { (void)device; *value = 40000; return 0; }
int nvmlDeviceGetPowerState(void *device, int *value) { (void)device; *value = 8; return 0; }
int nvmlDeviceGetTemperature(void *device, int kind, unsigned *value) { (void)device; (void)kind; *value = 30; return 0; }
int nvmlDeviceGetMemoryInfo(void *device, memory_info *value) {
    (void)device;
    if (getenv("NOVA_FIXTURE_NO_VRAM")) return 3;
    value->total = 32ull << 30;
    value->used = value->total * (getenv("NOVA_FIXTURE_DOT_WAVE") ? 70 + wave()/4 : 75 + samples % 3 * 5) / 100;
    value->free = value->total - value->used;
    return 0;
}
int nvmlDeviceGetPcieThroughput(void *device, int kind, unsigned *value) { (void)device; *value = kind == 0 ? 6000 : 30000; return 0; }

#ifndef NOVA_FIXTURE_LEGACY
#include <sys/time.h>
#include <limits.h>

typedef struct { unsigned pid; unsigned long long memory; unsigned gpu_instance, compute_instance; } process_v2;
typedef struct { unsigned pid; unsigned long long memory; } process_v1;
typedef struct { unsigned pid; unsigned long long timestamp; unsigned sm, mem, enc, dec; } process_sample;
static unsigned fixture_pid(void) { const char *pid = getenv("NOVA_FIXTURE_PID"); return pid ? (unsigned)strtoul(pid, NULL, 10) : 60001; }
int nvmlDeviceGetMaxClockInfo(void *device, int kind, unsigned *value) {
    (void)device;
    if (getenv("NOVA_FIXTURE_NO_MAX")) return 3;
    *value = kind == 0 ? 1500 : 4050;
    return 0;
}
static int process_list(unsigned *count, process_v2 *entries, int graphics) {
    unsigned needed = graphics ? 2 : 1;
    if (getenv("NOVA_FIXTURE_NO_PROCS") || (!graphics && getenv("NOVA_FIXTURE_NO_COMPUTE"))) return 4;
    if (getenv("NOVA_FIXTURE_MANY")) needed = 30;
    if (!entries || *count < needed) { *count = needed; return 7; }
    if (getenv("NOVA_FIXTURE_RACE") && *count == needed) { *count = needed + 1; return 7; }
    for (unsigned i = 0; i < needed; ++i) {
        entries[i].pid = i == 0 ? fixture_pid() : 60001 + i;
        entries[i].memory = i == 1 ? ULLONG_MAX : (graphics ? 320ull : 300ull) << 20;
        entries[i].gpu_instance = entries[i].compute_instance = UINT_MAX;
    }
    *count = needed;
    return 0;
}
#if defined(NOVA_FIXTURE_V1)
static int process_list_v1(unsigned *count, process_v1 *entries, int graphics) {
    process_v2 data[30]; unsigned capacity = *count;
    int result = process_list(count, entries ? data : NULL, graphics);
    if (result == 0 && entries && *count <= capacity) {
        for (unsigned i = 0; i < *count; ++i) { entries[i].pid = data[i].pid; entries[i].memory = data[i].memory; }
    }
    return result;
}
int nvmlDeviceGetGraphicsRunningProcesses(void *device, unsigned *count, process_v1 *entries) { (void)device; return process_list_v1(count, entries, 1); }
int nvmlDeviceGetComputeRunningProcesses(void *device, unsigned *count, process_v1 *entries) { (void)device; return process_list_v1(count, entries, 0); }
#elif defined(NOVA_FIXTURE_V2)
int nvmlDeviceGetGraphicsRunningProcesses_v2(void *device, unsigned *count, process_v2 *entries) { (void)device; return process_list(count, entries, 1); }
int nvmlDeviceGetComputeRunningProcesses_v2(void *device, unsigned *count, process_v2 *entries) { (void)device; return process_list(count, entries, 0); }
#else
int nvmlDeviceGetGraphicsRunningProcesses_v3(void *device, unsigned *count, process_v2 *entries) { (void)device; return process_list(count, entries, 1); }
int nvmlDeviceGetComputeRunningProcesses_v3(void *device, unsigned *count, process_v2 *entries) { (void)device; return process_list(count, entries, 0); }
#endif
int nvmlDeviceGetProcessUtilization(void *device, process_sample *entries, unsigned *count, unsigned long long last) {
    (void)device; (void)last;
    if (getenv("NOVA_FIXTURE_NO_UTIL")) return 3;
    if (!entries || *count < 2) { *count = 2; return 7; }
    struct timeval now; gettimeofday(&now, NULL);
    unsigned long long timestamp = (unsigned long long)now.tv_sec * 1000000 + now.tv_usec;
    if (getenv("NOVA_FIXTURE_STALE")) timestamp -= 10000000;
    entries[0] = (process_sample){fixture_pid(), timestamp, 67, 2, 0, 0};
    entries[1] = (process_sample){60002, timestamp, 33, 0, 0, 0};
    *count = 2;
    return 0;
}
#endif
