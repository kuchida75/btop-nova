/* Copyright 2026. Licensed under the Apache License, Version 2.0. */
#include "btop_zram.hpp"
#include <fstream>
#include <unordered_map>

namespace Zram {
namespace {
	Snapshot snapshot;
	bool initialized = false;
	std::optional<uint64_t> read_number(const std::filesystem::path& path) {
		std::ifstream input(path);
		std::string text;
		uint64_t result{};
		if (input >> text and number(text, result)) return result;
		return {};
	}
}

Snapshot read(const std::filesystem::path& sys_block, const std::filesystem::path& swaps) {
	Snapshot result;
	std::unordered_map<std::string, uint64_t> swap_used;
	std::ifstream swap_file(swaps);
	for (std::string line; std::getline(swap_file, line);) {
		std::istringstream fields(line);
		std::string name, type, capacity, used;
		uint64_t value{};
		if (fields >> name >> type >> capacity >> used and name.starts_with("/dev/zram")
			and device_name(name.substr(5)) and number(used, value)
			and value <= std::numeric_limits<uint64_t>::max() / 1024) swap_used[name.substr(5)] = value * 1024;
	}
	std::error_code error;
	std::filesystem::directory_iterator entry(sys_block, error), end;
	for (; not error and entry != end; entry.increment(error)) {
		const auto path = entry->path();
		Device device;
		device.name = path.filename().string();
		if (not device_name(device.name)) continue;
		const auto capacity = read_number(path / "disksize");
		if (capacity and *capacity == 0) continue; // Unconfigured device.
		if (not capacity and read_number(path / "initstate") == std::optional<uint64_t>{0}) continue;
		device.capacity_valid = capacity.has_value();
		device.capacity = capacity.value_or(0);
		std::ifstream stats_file(path / "mm_stat");
		const auto stats = parse_stats(stats_file);
		device.stats_valid = stats.has_value();
		device.stats = stats.value_or(Stats{});
		std::ifstream algorithms(path / "comp_algorithm");
		device.algorithm = algorithm(algorithms);
		if (const auto swap = swap_used.find(device.name); swap != swap_used.end()) {
			device.swap = device.swap_known = true;
			device.swap_used = swap->second;
		}
		result.devices.push_back(device);
	}
	return result;
}

const Snapshot& current() { return snapshot; }
const Snapshot& collect(bool no_update) {
	if (no_update and initialized) return snapshot;
	initialized = true;
#ifdef __linux__
	snapshot = read("/sys/block", "/proc/swaps");
#else
	snapshot = {};
#endif
	return snapshot;
}
}
