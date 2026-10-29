/* Test-only network counters/interfaces. No real traffic or link changes. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
static struct ifaddrs device;
static struct sockaddr_in address;
static int connected(void) {
    const char *root=getenv("NOVA_TEST_NET_FILES"); char path[PATH_MAX],mode[16]={0};
    snprintf(path,sizeof(path),"%s/state",root);
    FILE *(*open_original)(const char *,const char *)=dlsym(RTLD_NEXT,"fopen");
    FILE *file=open_original(path,"r");
    if(file) { (void)fscanf(file,"%15s",mode); fclose(file); }
    return strcmp(mode,"down")!=0;
}
int getifaddrs(struct ifaddrs **result) {
    if(!getenv("NOVA_TEST_NET_FILES")) {
        int (*original)(struct ifaddrs **)=dlsym(RTLD_NEXT,"getifaddrs"); return original(result);
    }
    memset(&device,0,sizeof(device)); memset(&address,0,sizeof(address));
    address.sin_family=AF_INET; address.sin_addr.s_addr=0x0100007f;
    device.ifa_name="lo"; device.ifa_flags=IFF_UP | (connected()?IFF_RUNNING:0);
    device.ifa_addr=(struct sockaddr *)&address; *result=&device; return 0;
}
void freeifaddrs(struct ifaddrs *list) {
    if(list!=&device) { void (*original)(struct ifaddrs *)=dlsym(RTLD_NEXT,"freeifaddrs"); original(list); }
}
static FILE *mapped(const char *symbol,const char *path,const char *mode) {
    FILE *(*original)(const char *,const char *)=dlsym(RTLD_NEXT,symbol);
    const char *root=getenv("NOVA_TEST_NET_FILES"); char target[PATH_MAX];
    const char *prefix="/sys/class/net/lo/statistics/";
    if(root && !strncmp(path,prefix,strlen(prefix)) && !strcmp(mode,"r")) {
        snprintf(target,sizeof(target),"%s/%s",root,path+strlen(prefix)); path=target;
    }
    return original(path,mode);
}
FILE *fopen(const char *path,const char *mode) { return mapped("fopen",path,mode); }
FILE *fopen64(const char *path,const char *mode) { return mapped("fopen64",path,mode); }
