#include "btop_mounts.hpp"
#include <fstream>
#ifdef __linux__
#include <sys/statvfs.h>
#endif

namespace Mounts {
Layout layout;
namespace {
	std::vector<Entry> entries;
	std::string message;
	bool initialized = false;
}

const std::vector<Entry>& current() { return entries; }
const std::string& status() { return message; }

const std::vector<Entry>& collect(bool no_update) {
	if (no_update and initialized) return entries;
	initialized = true;
	message.clear();
#ifdef __linux__
	std::ifstream mounts("/proc/self/mountinfo");
	if (not mounts) {
		entries.clear();
		message = "Unable to read mounted filesystems";
		return entries;
	}
	auto updated = parse_mountinfo(mounts);
	for (auto& entry : updated) {
		struct statvfs stats{};
		if (statvfs(entry.mountpoint.c_str(), &stats) != 0) continue;
		const uint64_t unit = stats.f_frsize ? stats.f_frsize : stats.f_bsize;
		entry.total = stats.f_blocks * unit;
		// Match duf: USED is allocated blocks; AVAIL excludes reserved blocks.
		entry.used = (stats.f_blocks - std::min(stats.f_blocks, stats.f_bfree)) * unit;
		entry.available = stats.f_bavail * unit;
		entry.used_percent = entry.total ? 100.0 * entry.used / entry.total : 0;
		entry.valid = entry.total > 0;
	}
	entries = std::move(updated);
#else
	entries.clear();
	message = "Mount table is available on Linux";
#endif
	return entries;
}
}
