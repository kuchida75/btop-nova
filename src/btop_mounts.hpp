// Nova mounted-filesystem summary. Linux mountinfo parsing and layout helpers.
#pragma once
#include <algorithm>
#include <cstdint>
#include <istream>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

namespace Mounts {

struct Entry {
	std::string mountpoint, device, fstype, identity, root;
	uint64_t total{}, used{}, available{};
	double used_percent{};
	bool valid{};
};

inline std::string decode_field(const std::string& field) {
	std::string out;
	for (size_t i = 0; i < field.size(); ++i) {
		if (field[i] == '\\' and i + 3 < field.size()
			and field[i+1] >= '0' and field[i+1] <= '7'
			and field[i+2] >= '0' and field[i+2] <= '7'
			and field[i+3] >= '0' and field[i+3] <= '7') {
			out += char((field[i+1]-'0')*64 + (field[i+2]-'0')*8 + field[i+3]-'0');
			i += 3;
		}
		else out += field[i];
	}
	return out;
}

inline std::string display_text(std::string text) {
	// Mounted names are data, including when they contain terminal controls.
	for (auto& c : text) if (static_cast<unsigned char>(c) < 32 or c == 127) c = '?';
	return text;
}

inline std::vector<Entry> parse_mountinfo(std::istream& input) {
	std::vector<Entry> entries;
	for (std::string line; std::getline(input, line);) {
		std::istringstream fields(line);
		std::vector<std::string> words;
		for (std::string word; fields >> word;) words.push_back(word);
		auto separator = std::find(words.begin(), words.end(), "-");
		if (words.size() < 10 or separator == words.end() or separator < words.begin()+6 or words.end() - separator < 4) continue;
		Entry entry;
		entry.identity = words[2];
		entry.root = decode_field(words[3]);
		entry.mountpoint = decode_field(words[4]);
		entry.fstype = *(separator + 1);
		entry.device = decode_field(*(separator + 2));
		if (not (entry.device.starts_with("/dev/") or entry.fstype == "zfs")) continue;
		if (entry.device.starts_with("/dev/loop") or entry.fstype == "squashfs") continue;
		// Exclude directory bind mounts; Btrfs subvolumes remain distinct rows.
		if (entry.root != "/" and entry.fstype != "btrfs" and entry.fstype != "zfs") continue;
		auto duplicate = std::find_if(entries.begin(), entries.end(), [&](const auto& other) {
			return other.identity == entry.identity and other.root == entry.root and other.fstype == entry.fstype;
		});
		if (duplicate == entries.end()) entries.push_back(entry);
		else if (entry.mountpoint.size() < duplicate->mountpoint.size()) *duplicate = entry;
	}
	std::sort(entries.begin(), entries.end(), [](const auto& a, const auto& b) { return a.mountpoint < b.mountpoint; });
	return entries;
}

inline int table_height(int height, int width, int count, bool detailed, bool enabled) {
	const int available = height - (detailed ? 8 : 0);
	// Keep at least ten process rows and give mounts at most a third of the box.
	if (not enabled or width < 44 or available < 18) return 0;
	return std::min({std::max(1, count) + 4, available / 3, available - 13});
}

inline int full_table_height(int height, int width, int count, bool detailed, bool enabled, int left_minimum) {
	const int result = std::min(table_height(height, width, count, detailed, enabled), std::max(0, height - left_minimum));
	return result >= 5 ? result : 0;
}

// Whole-width table shares the body budget with memory, network and processes.
struct Layout {
	bool full_width{};
	int body_height{}, left_minimum{}, y{}, width{}, height{};
};
extern Layout layout;

struct Columns {
	int mount{14}, size{5}, used{5}, available{5}, percent{6}, type{}, device{}, bar{};
	int usage() const { return percent + (bar ? bar + 3 : 0); }
	int total() const { return mount + size + used + available + usage() + type + device + 4 + (type ? 1 : 0) + (device ? 1 : 0); }
};

inline Columns columns(int interior_width, int longest_mount, int longest_device, bool stretch = false) {
	Columns result;
	if (interior_width >= 59) { result.type = 5; result.size = result.used = result.available = 6; }
	if (interior_width >= 76) result.device = 14;
	int spare = std::max(0, interior_width - result.total());
	int add = std::min(spare, std::max(0, std::min(32, longest_mount) - result.mount));
	result.mount += add; spare -= add;
	if (stretch) {
		// At full width, put spare space into the visual usage bar, keeping
		// device names readable instead of leaving a large blank path column.
		if (result.device) {
			add = std::min(spare, std::max(0, longest_device - result.device));
			result.device += add; spare -= add;
		}
		if (spare >= 7) { result.bar = spare - 3; spare = 0; }
		result.mount += spare;
		return result;
	}
	if (spare >= 7) {
		result.bar = std::min(10, std::max(4, spare / 2 - 3));
		spare -= result.bar + 3;
	}
	if (result.device) {
		add = std::min(spare, std::max(0, longest_device - result.device));
		result.device += add; spare -= add;
	}
	result.mount += spare;
	return result;
}

inline std::string format_bytes(uint64_t bytes, bool decimal, int width) {
	const double base = decimal ? 1000 : 1024;
	const std::string units = "BKMGTPE";
	double value = bytes;
	size_t unit = 0;
	while (value >= base and unit + 1 < units.size()) { value /= base; ++unit; }
	std::ostringstream output;
	output << std::fixed << std::setprecision(unit ? 1 : 0) << value << units[unit];
	auto text = output.str();
	if ((int)text.size() > width) {
		output.str(""); output.clear();
		output << std::fixed << std::setprecision(0) << value << units[unit];
		text = output.str();
	}
	return text;
}

const std::vector<Entry>& collect(bool no_update = false);
const std::vector<Entry>& current();
const std::string& status();
std::string draw(int x, int y, int width, int height);

}
