/* Copyright 2026. Licensed under the Apache License, Version 2.0. */
#pragma once
#include <algorithm>
#include <charconv>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <istream>
#include <string>
#include <string_view>
#include <vector>

namespace CpuFrequency {

inline std::string_view trim(std::string_view value) {
	const auto first = value.find_first_not_of(" \t\r\n");
	if (first == value.npos) return {};
	return value.substr(first, value.find_last_not_of(" \t\r\n") - first + 1);
}

// Unknown values are -1, never a CPU header clock copied to every thread.
inline int parse_mhz(std::string_view text, double divisor = 1.0) {
	text = trim(text);
	if (text.empty()) return -1;
	double value = 0;
	const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value);
	if (error != std::errc{} or end != text.data() + text.size() or not std::isfinite(value)) return -1;
	value /= divisor;
	return value >= 1 and value <= 99999 ? static_cast<int>(std::lround(value)) : -1;
}

inline std::vector<int> parse_cpuinfo(std::istream& input, int count) {
	std::vector<int> values(std::max(0, count), -1);
	int processor = -1;
	for (std::string line; std::getline(input, line);) {
		const auto colon = line.find(':');
		if (colon == line.npos) continue;
		const auto key = trim(std::string_view(line).substr(0, colon));
		const auto value = trim(std::string_view(line).substr(colon + 1));
		if (key == "processor") {
			if (value.empty()) { processor = -1; continue; }
			int id = -1;
			const auto [end, error] = std::from_chars(value.data(), value.data() + value.size(), id);
			processor = error == std::errc{} and end == value.data() + value.size() and id >= 0 and id < count ? id : -1;
		}
		else if (key == "cpu MHz" and processor >= 0) values[processor] = parse_mhz(value);
	}
	return values;
}

inline std::vector<int> collect(int count, const std::filesystem::path& cpu_root = "/sys/devices/system/cpu",
		const std::filesystem::path& cpuinfo = "/proc/cpuinfo") {
	std::vector<int> values(std::max(0, count), -1);
	std::vector<bool> online(values.size(), true);
	bool needs_fallback = false;
	for (int id = 0; id < count; ++id) {
		const auto path = cpu_root / ("cpu" + std::to_string(id));
		int state = 1;
		std::ifstream(path / "online") >> state;
		if (state == 0) { online[id] = false; continue; }
		std::ifstream input(path / "cpufreq/scaling_cur_freq");
		std::string value;
		if (std::getline(input, value)) values[id] = parse_mhz(value, 1000.0);
		needs_fallback |= values[id] < 0;
	}
	if (needs_fallback) {
		std::ifstream input(cpuinfo);
		const auto fallback = parse_cpuinfo(input, count);
		for (int id = 0; id < count; ++id)
			if (online[id] and values[id] < 0) values[id] = fallback[id];
	}
	return values;
}

struct Layout {
	int columns, rows, id_width, cell_width, box_width, box_height, cpu_height, padding;
	bool fits_width;
};

inline Layout layout(int width, int count, bool temperatures, int extra_rows = 0) {
	count = std::max(1, count);
	const int columns = std::min(3, count);
	const int rows = (count + columns - 1) / columns;
	const int id_width = static_cast<int>(std::to_string(count - 1).size());
	// C + ID + space, usage%, space + five-digit MHz, temperature, separator.
	const int content = 2 + id_width + 4 + 9 + (temperatures ? 6 : 0) + 1;
	// Keep three compact value columns; all surplus width belongs to the history.
	const int minimum_box = columns * content + 1;
	const int cell = content;
	const int box = columns * cell + 1;
	return {columns, rows, id_width, cell, box, rows + 4 + extra_rows,
		rows + 6 + extra_rows, cell - content, minimum_box <= width - 2 - 12};
}

}
