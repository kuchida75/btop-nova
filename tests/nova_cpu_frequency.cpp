#include "../src/btop_cpu_frequency.hpp"
#include <cassert>
#include <chrono>
#include <iostream>
#include <sstream>

int main(int argc, char** argv) {
	using namespace CpuFrequency;
	if (argc == 3 and std::string(argv[1]) == "--bench") {
		const auto start = std::chrono::steady_clock::now();
		for (int i = 0; i < 100; ++i) collect(std::stoi(argv[2]));
		std::cout << "Per-thread collection average over 100 samples: "
			<< std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count() / 100 << " ms\n";
		return 0;
	}
	if (argc == 3 and std::string(argv[1]) == "--dump") {
		const auto values = collect(std::stoi(argv[2]));
		for (size_t id = 0; id < values.size(); ++id) std::cout << id << '\t' << values[id] << '\n';
		return 0;
	}
	assert(argc == 2);
	for (const auto* text : {"", " ", "0", "-1", "NaN", "inf", "1e300", "123MHz", "100000", "1 2"})
		assert(parse_mhz(text) == -1);
	assert(parse_mhz(" 5499.6\n") == 5500);
	assert(parse_mhz("800000\n", 1000) == 800);
	assert(parse_mhz("99999000", 1000) == 99999);
	std::istringstream info("processor : 3\ncpu MHz : 3200.4\nprocessor: 0\ncpu MHz: 800.8\nprocessor: bad\ncpu MHz: 9999\nprocessor: 99\ncpu MHz: 9999\nprocessor:\ncpu MHz: 9999\n");
	assert((parse_cpuinfo(info, 5) == std::vector<int>{801, -1, -1, 3200, -1}));
	const std::filesystem::path root = argv[1];
	auto write = [&](const auto& path, const std::string& value) {
		std::filesystem::create_directories(path.parent_path()); std::ofstream(path) << value;
	};
	write(root / "cpu0/cpufreq/scaling_cur_freq", "5200000\n");
	write(root / "cpu2/cpufreq/scaling_cur_freq", "4000000\n");
	write(root / "cpu2/online", "0\n");
	write(root / "cpu3/cpufreq/scaling_cur_freq", "broken\n");
	write(root / "cpuinfo", "processor: 1\ncpu MHz: 1200.2\nprocessor: 2\ncpu MHz: 1400\nprocessor: 3\ncpu MHz: 5300.6\n");
	assert((collect(5, root, root / "cpuinfo") == std::vector<int>{5200, 1200, -1, 5301, -1}));
	write(root / "cpu0/cpufreq/scaling_cur_freq", "800000\n");
	assert(collect(5, root, root / "cpuinfo")[0] == 800);
	std::filesystem::remove(root / "cpu0/cpufreq/scaling_cur_freq");
	assert(collect(5, root, root / "cpuinfo")[0] == -1); // No stale samples.
	write(root / "cpu2/online", "1\n");
	assert(collect(5, root, root / "cpuinfo")[2] == 4000); // Online transitions.
	assert(collect(0, root, root / "missing").empty());
	const auto full = layout(146, 32, true);
	assert(full.columns == 3 and full.rows == 11 and full.cpu_height == 17 and full.box_width == 73 and full.fits_width);
	assert(full.padding == 0);
	const auto narrow = layout(87, 32, true);
	assert(narrow.fits_width and narrow.box_width == 73 and narrow.padding == 0);
	assert(87 - narrow.box_width - 2 == 12);
	assert(not layout(86, 32, true).fits_width);
	assert(layout(80, 32, false).fits_width);
	assert(layout(146, 32, true, 2).cpu_height == 19);
	for (int count : {1, 2, 3, 4, 7, 32, 64, 128, 1024})
		for (bool temps : {false, true})
			for (int width = 60; width <= 300; ++width) {
				const auto l = layout(width, count, temps);
				assert(l.columns >= 1 and l.columns <= 3 and l.rows * l.columns >= count);
				assert(l.box_width == l.columns * l.cell_width + 1 and l.box_height + 2 == l.cpu_height);
				assert(l.padding >= 0);
				assert(not l.fits_width or width - l.box_width - 2 >= 12);
			}
	std::cout << "Per-CPU sysfs/fallback mapping, invalid/offline/missing/stale data, online transitions and three-column bounds passed\n";
}
