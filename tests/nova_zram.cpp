#include "../src/btop_zram.hpp"
#include <cassert>
#include <fstream>
#include <iostream>

using namespace Zram;
static void write(const std::filesystem::path& path, const std::string& text) {
	std::ofstream file(path); file << text;
}

int main(int argc, char** argv) {
	if (argc == 2 and std::string(argv[1]) == "--dump") {
		for (const auto& d : collect().devices)
			std::cout << d.name << '\t' << d.algorithm << '\t' << d.capacity << '\t' << d.stats.original << '\t' << d.stats.compressed
				<< '\t' << d.stats.memory << '\t' << d.stats_valid << '\t' << d.swap_known << '\t' << d.swap_used << '\n';
		return 0;
	}
	assert(argc == 2); // Temporary fixture root supplied by the test runner.
	assert(device_name("zram0") and device_name("zram123"));
	assert(not device_name("zram") and not device_name("zram-control") and not device_name("sda"));
	for (const auto& bad : {"", "1 2", "-1 2 3", "1 x 3", "1 2 -1", "18446744073709551616 2 3", "1a 2 3"}) {
		std::istringstream input(bad); assert(not parse_stats(input));
	}
	std::istringstream older("1000 250 320 0 320 0 0");
	const auto parsed = parse_stats(older); assert(parsed and parsed->memory == 320);
	std::istringstream modern("1000 250 320 0 320 0 0 0 0 9999"); assert(parse_stats(modern));
	std::istringstream algorithms("lzo lz4 [zstd] 842"); assert(algorithm(algorithms) == "zstd");
	std::istringstream unavailable("lz4 zstd"); assert(algorithm(unavailable) == "--");
	std::istringstream control("[zstd\x1b]"); assert(algorithm(control) == "--");

	const std::filesystem::path fixture = argv[1];
	const auto block = fixture / "block"; std::filesystem::create_directories(block / "zram0");
	write(block / "zram0/disksize", "8589934592\n");
	write(block / "zram0/mm_stat", "4294967296 1073741824 1207959552 0 0 0 0 0 0\n");
	write(block / "zram0/comp_algorithm", "lz4 [zstd]\n");
	write(fixture / "swaps", "Filename Type Size Used Priority\n/dev/zram0 partition 8388608 4194304 100\n/swap.img file 8388608 0 -1\n");
	std::filesystem::create_directory(block / "zram1"); write(block / "zram1/disksize", "0\n");
	std::filesystem::create_directory(block / "sda"); write(block / "sda/disksize", "123\n");
	auto snapshot = read(block, fixture / "swaps"); assert(snapshot.devices.size() == 1);
	assert(in_use(snapshot));
	const auto data = summarize(snapshot);
	assert(data.capacity == 8ULL * 1024 * 1024 * 1024 and data.algorithm == "zstd");
	assert(data.stats_valid and not data.idle and data.memory == 1207959552);
	const auto lines = footer(data, 40, false);
	assert(lines[0] == "ZRAM zstd cap8.0G");
	assert(lines[1] == "Data 4.0G>1.0G 4.0x");
	assert(lines[2] == "RAM 1.1G Save 2.9G");
	assert(footer(data, 40, true)[1] == "Data 4.3G>1.1G 4.0x");
	auto high_ratio = data; high_ratio.compressed = 1;
	assert(footer(high_ratio, 21, false)[1].ends_with(">999x"));
	for (int width = 0; width <= 100; ++width) for (const auto& line : footer(data, width, false)) assert((int)line.size() <= width);

	// Fresh collection reflects changing counters, without a cached zero.
	write(block / "zram0/mm_stat", "4096 59 20480 0 20480 0 0 0 0\n");
	write(fixture / "swaps", "Filename Type Size Used Priority\n/dev/zram0 partition 8388608 0 100\n");
	const auto idle = summarize(read(block, fixture / "swaps"));
	assert(idle.original == 4096 and idle.idle);
	assert(not in_use(read(block, fixture / "swaps")));
	assert(footer_rows(30, 35, 4, true, in_use(read(block, fixture / "swaps"))) == 0);
	assert(footer(idle, 40, false)[1] == "Data 4.0K>59B idle");
	assert(footer(idle, 40, false)[2] == "RAM 20.0K Save -16.0K");
	write(block / "zram0/mm_stat", "1048576 0 0 0 0 256 0 0 0\n");
	write(fixture / "swaps", "Filename Type Size Used Priority\n/dev/zram0 partition 8388608 1024 100\n");
	const auto same_pages = summarize(read(block, fixture / "swaps"));
	assert(not same_pages.idle and footer(same_pages, 40, false)[1] == "Data 1.0M>0B --");
	assert(in_use(read(block, fixture / "swaps"))); // auto-restores after idle

	// Missing or malformed stats stay unknown; partial data is never summed
	// into a plausible-looking ratio for all devices.
	write(block / "zram0/mm_stat", "not readable stats\n");
	const auto bad = summarize(read(block, fixture / "swaps"));
	assert(not bad.stats_valid and footer(bad, 40, false)[1] == "Data -- (unavailable)");
	assert(in_use(read(block, fixture / "swaps"))); // known usage, unknown compression
	write(fixture / "swaps", "Filename Type Size Used Priority\n/dev/zram0 partition 8388608 0 100\n");
	assert(not in_use(read(block, fixture / "swaps"))); // known idle even with unavailable mm_stat
	write(fixture / "swaps", "Filename Type Size Used Priority\n/dev/zram0 partition 8388608 1024 100\n");
	write(block / "zram1/disksize", "8589934592\n");
	write(block / "zram1/mm_stat", "4294967296 1073741824 1207959552\n");
	write(block / "zram1/comp_algorithm", "[lz4]\n");
	const auto partial = summarize(read(block, fixture / "swaps"));
	assert(partial.devices == 2 and partial.capacity == 16ULL * 1024 * 1024 * 1024 and not partial.stats_valid and partial.algorithm == "mixed");
	write(block / "zram0/mm_stat", "4294967296 1073741824 1207959552\n");
	const auto multiple = summarize(read(block, fixture / "swaps"));
	assert(multiple.stats_valid and multiple.original == 8ULL * 1024 * 1024 * 1024);
	assert(footer(multiple, 40, false)[0] == "ZRAM 2 mixed cap16.0G");
	std::filesystem::remove(block / "zram0/disksize");
	assert(not summarize(read(block, fixture / "swaps")).capacity_valid);
	assert(read(fixture / "absent", fixture / "swaps").devices.empty());
	assert(not in_use({}));
	Device filesystem{"zram2", "lz4", 8192, 0, {4096, 32, 4096}, true, true, false, false};
	assert(in_use({{filesystem}})); // initialized devices used as filesystems
	filesystem.stats.original = 0;
	assert(not in_use({{filesystem}}));
	filesystem.stats_valid = false;
	assert(in_use({{filesystem}})); // cannot declare an unreadable device idle
	Snapshot overflow;
	Device maximum{"zram0", "zstd", UINT64_MAX, 0, {UINT64_MAX, 0, 0}, true, true, false, false};
	overflow.devices = {maximum, maximum};
	assert(not summarize(overflow).capacity_valid and not summarize(overflow).stats_valid);
	for (int height = 10; height <= 100; ++height) for (int width = 1; width <= 100; ++width) for (int items : {4, 6}) {
		const int rows = footer_rows(height, width, items, true, true);
		assert(rows == 0 or (rows == 3 and height - rows >= items * 2 + 6 and width >= 21));
		assert(footer_rows(height, width, items, false, true) == 0);
		assert(footer_rows(height, width, items, true, false) == 0);
	}
	std::cout << "Zram ABI parsing, real RAM cost, automatic active/idle visibility, idle header, negative savings, same pages, multiple devices, missing data, refresh and footer bounds passed\n";
}
