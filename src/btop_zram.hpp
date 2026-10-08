/* Copyright 2026. Licensed under the Apache License, Version 2.0. */
#pragma once
#include <array>
#include <charconv>
#include <cstdint>
#include <filesystem>
#include <iomanip>
#include <limits>
#include <optional>
#include <sstream>
#include <string>
#include <vector>
#include "btop_mounts.hpp"

namespace Zram {

struct Stats { uint64_t original{}, compressed{}, memory{}; };
struct Device {
	std::string name, algorithm;
	uint64_t capacity{}, swap_used{};
	Stats stats;
	bool capacity_valid{}, stats_valid{}, swap{}, swap_known{};
};
struct Snapshot { std::vector<Device> devices; };
struct Summary {
	int devices{};
	uint64_t capacity{}, original{}, compressed{}, memory{};
	std::string algorithm;
	bool capacity_valid{true}, stats_valid{true}, idle{};
};

inline bool device_name(const std::string& name) {
	return name.size() > 4 and name.starts_with("zram")
		and name.find_first_not_of("0123456789", 4) == std::string::npos;
}
inline bool number(const std::string& text, uint64_t& value) {
	const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
	return not text.empty() and result.ec == std::errc{} and result.ptr == text.data() + text.size();
}
inline std::optional<Stats> parse_stats(std::istream& input) {
	// The first three mm_stat fields are bytes, including allocator overhead
	// in the third field. Newer kernels append more fields to the same ABI.
	std::array<uint64_t, 3> values{};
	for (auto& value : values) {
		std::string text;
		if (not (input >> text) or not number(text, value)) return {};
	}
	return Stats{values[0], values[1], values[2]};
}
inline std::string algorithm(std::istream& input) {
	for (std::string word; input >> word;)
		if (word.size() > 2 and word.front() == '[' and word.back() == ']') {
			word = word.substr(1, word.size() - 2);
			if (word.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-") == std::string::npos)
				return word;
		}
	return "--";
}
inline bool add(uint64_t& total, uint64_t value) {
	if (value > std::numeric_limits<uint64_t>::max() - total) return false;
	total += value;
	return true;
}
inline Summary summarize(const Snapshot& snapshot) {
	Summary result;
	bool idle_swap = not snapshot.devices.empty();
	for (const auto& device : snapshot.devices) {
		++result.devices;
		result.capacity_valid &= device.capacity_valid and add(result.capacity, device.capacity);
		result.stats_valid &= device.stats_valid and add(result.original, device.stats.original)
			and add(result.compressed, device.stats.compressed) and add(result.memory, device.stats.memory);
		if (result.algorithm.empty()) result.algorithm = device.algorithm;
		else if (result.algorithm != device.algorithm) result.algorithm = "mixed";
		idle_swap &= device.swap and device.swap_known and device.swap_used == 0;
	}
	// An idle swap device can still hold its tiny swap header. Its apparent
	// compression ratio is not representative of a real swapped workload.
	result.idle = result.stats_valid and (result.original == 0 or idle_swap);
	return result;
}
inline bool in_use(const Snapshot& snapshot) {
	for (const auto& device : snapshot.devices) {
		// /proc/swaps distinguishes real workload pages from the swap header
		// that remains compressed even while Used is zero.
		if (device.swap and device.swap_known) {
			if (device.swap_used > 0) return true;
		}
		else if (not device.stats_valid or device.stats.original > 0) return true;
	}
	return false;
}
inline int footer_rows(int height, int width, int memory_items, bool enabled, bool active) {
	// Retain all normal RAM metrics and any explicitly enabled swap metrics.
	return enabled and active and width >= 21 and height >= 2 * memory_items + 9 ? 3 : 0;
}
inline std::array<std::string, 3> footer(const Summary& data, int width, bool decimal) {
	if (width <= 0) return {};
	const auto size = [decimal](uint64_t value) { return Mounts::format_bytes(value, decimal, 5); };
	const auto fit = [width](std::string value) { if ((int)value.size() > width) value.resize(width); return value; };
	std::array<std::string, 3> result;
	const std::string prefix = "ZRAM " + (data.devices > 1 ? std::to_string(data.devices) + " " : "");
	const std::string capacity = "cap" + (data.capacity_valid ? size(data.capacity) : "--");
	result[0] = prefix + data.algorithm + " " + capacity;
	if ((int)result[0].size() > width) result[0] = prefix + capacity;
	if (not data.stats_valid) {
		result[1] = "Data -- (unavailable)";
		result[2] = "RAM -- Save --";
	}
	else {
		std::string ratio = "--";
		if (data.idle) ratio = "idle";
		else if (data.compressed > 0 and data.original > 0) {
			const double value = (double)data.original / data.compressed;
			std::ostringstream text;
			text << std::fixed << std::setprecision(1) << value << 'x';
			ratio = value >= 1000 ? ">999x" : text.str();
		}
		const std::string sizes = size(data.original) + ">" + size(data.compressed) + " " + ratio;
		result[1] = "Data " + sizes;
		if ((int)result[1].size() > width) result[1] = sizes;
		const bool saved = data.original >= data.memory;
		const std::string saving = (saved ? "" : "-") + size(saved ? data.original - data.memory : data.memory - data.original);
		result[2] = "RAM " + size(data.memory) + " Save " + saving;
	}
	for (auto& line : result) line = fit(line);
	return result;
}

Snapshot read(const std::filesystem::path& sys_block, const std::filesystem::path& swaps);
const Snapshot& collect(bool no_update = false);
const Snapshot& current();

}
