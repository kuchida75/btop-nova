/* Copyright 2026. Licensed under the Apache License, Version 2.0. */
#pragma once
#include <algorithm>
#include <cerrno>
#include <charconv>
#include <cstdint>
#include <deque>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace CpuPower {
struct Reading {
	long long milliwatts = -1;
	std::string status = "unavailable";
};
struct Sample {
	long long load = -1, milliwatts = -1;
	uint64_t timestamp = 0;
};
inline bool number(const std::filesystem::path& path, uint64_t& value, bool& denied) {
	errno = 0;
	std::ifstream file(path);
	if (not file) { denied |= errno == EACCES or errno == EPERM; return false; }
	std::string text, extra;
	if (not (file >> text) or (file >> extra)) return false;
	const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
	return result.ec == std::errc{} and result.ptr == text.data() + text.size();
}
struct Counter {
	uint64_t energy = 0, range = 0, timestamp = 0;
	bool ready = false;
	long long update(uint64_t current, uint64_t maximum, uint64_t now) {
		const auto previous = *this;
		*this = {current, maximum, now, maximum > 0 and current <= maximum};
		if (not ready or not previous.ready or maximum != previous.range or now <= previous.timestamp or now - previous.timestamp > 60000) return -1;
		uint64_t delta = 0;
		if (current >= previous.energy) delta = current - previous.energy;
		else {
			// A decrease away from the rollover boundary is a reset, not a spike.
			if (previous.energy < maximum - maximum / 4 or current > maximum / 4) return -1;
			delta = maximum - previous.energy + current;
		}
		const long double mw = static_cast<long double>(delta) / (now - previous.timestamp);
		// Reject implausible discontinuities; never clip a broken counter into a graph.
		return mw <= 10000000 ? static_cast<long long>(mw + .5L) : -1;
	}
};
class Collector {
	std::filesystem::path root;
	std::map<std::filesystem::path, Counter> counters;
public:
	explicit Collector(std::filesystem::path path = "/sys/class/powercap") : root(std::move(path)) {}
	void reset() { counters.clear(); }
	Reading collect(uint64_t now) {
		namespace fs = std::filesystem;
		std::vector<fs::path> pending{root}, zones;
		std::set<fs::path> visited;
		// Follow only RAPL control/zone links, never generic device/subsystem links.
		for (size_t i = 0; i < pending.size() and i < 256; ++i) {
			std::error_code error;
			const auto path = fs::canonical(pending[i], error);
			if (error or not visited.insert(path).second) continue;
			std::ifstream name_file(path / "name"); std::string name; name_file >> name;
			if (name.starts_with("package-") and name.size() > 8
				and std::all_of(name.begin() + 8, name.end(), [](char c) { return c >= '0' and c <= '9'; })) {
				zones.push_back(path); continue; // Package includes its subdomains.
			}
			for (fs::directory_iterator it(path, fs::directory_options::skip_permission_denied, error), end; not error and it != end; it.increment(error)) {
				const auto& entry = *it;
				const auto filename = entry.path().filename().string();
				if (filename == "intel-rapl" or filename.starts_with("intel-rapl:")
					or filename == "amd-rapl" or filename.starts_with("amd-rapl:")) pending.push_back(entry.path());
			}
		}
		if (zones.empty()) { reset(); return {-1, "unavailable"}; }
		std::map<fs::path, Counter> next;
		long long total = 0; bool missing = false, denied = false;
		for (const auto& path : zones) {
			uint64_t energy = 0, maximum = 0;
			if (not number(path / "energy_uj", energy, denied) or not number(path / "max_energy_range_uj", maximum, denied)) {
				missing = true; continue;
			}
			auto counter = counters.contains(path) ? counters.at(path) : Counter{};
			const auto mw = counter.update(energy, maximum, now);
			next[path] = counter;
			if (mw < 0) missing = true;
			else total += mw;
		}
		counters.swap(next);
		// Never silently report a partial total on a multi-package system.
		return missing ? Reading{-1, denied ? "read access needed" : "sampling..."} : Reading{total, ""};
	}
};
inline long long scale_mw(const std::deque<Sample>& history, int visible) {
	long long peak = 0;
	const size_t first = history.size() - std::min(history.size(), static_cast<size_t>(std::max(0, visible)));
	for (size_t i = first; i < history.size(); ++i) peak = std::max(peak, history[i].milliwatts);
	return std::max(50000ll, ((peak + 49999) / 50000) * 50000);
}
}
