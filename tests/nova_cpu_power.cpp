#include "../src/btop_cpu_power.hpp"
#include <cassert>
#include <iostream>
#include <unistd.h>

int main(int argc, char** argv) {
	using namespace CpuPower;
	Counter counter;
	assert(counter.update(100000000, 1000000000, 1000) == -1);
	assert(counter.update(150000000, 1000000000, 2000) == 50000); // 50 J / 1 s.
	assert(counter.update(150000000, 1000000000, 2500) == 0);
	assert(counter.update(100000000, 1000000000, 3000) == -1); // Reset, not a wrap.
	assert(counter.update(110000000, 1000000000, 3500) == 20000);
	counter = {};
	assert(counter.update(900000000, 1000000000, 0) == -1);
	assert(counter.update(100000000, 1000000000, 1000) == 200000); // Rollover.
	assert(counter.update(150000000, 1000000000, 1000) == -1); // No elapsed time.
	assert(counter.update(200000000, 1000000000, 62000) == -1); // Long pause.
	assert(counter.update(210000000, 2000000000, 63000) == -1); // Range changed.
	assert(counter.update(220000000, 2000000000, 64000) == 10000);
	assert(counter.update(2000000001, 2000000000, 65000) == -1);
	assert(counter.update(0, 0, 66000) == -1);
	counter = {};
	assert(counter.update(0, 1000000000, 0) == -1);
	assert(counter.update(500000000, 1000000000, 1) == -1); // Discontinuity.
	assert(argc == 2);
	namespace fs = std::filesystem;
	const fs::path root = argv[1]; fs::create_directories(root);
	const auto write = [&](const fs::path& p, const std::string& text) { fs::create_directories(p.parent_path()); std::ofstream(p) << text; };
	const auto zero = root / "intel-rapl/intel-rapl:0";
	const auto one = root / "intel-rapl/intel-rapl:1";
	for (const auto& p : {zero, one}) {
		write(p / "name", p == zero ? "package-0" : "package-1");
		write(p / "max_energy_range_uj", "1000000000");
		write(p / "energy_uj", p == zero ? "100000000" : "200000000");
		write(p / "enabled", "0"); // Controls can be disabled while counters work.
	}
	fs::create_directory_symlink(zero, root / "intel-rapl:0"); // Same package exposed twice.
	write(zero / "intel-rapl:0:0/name", "core");
	write(zero / "intel-rapl:0:0/energy_uj", "900000000"); // Never double-count subdomains.
	write(root / "intel-rapl-mmio/intel-rapl-mmio:0/name", "package-0");
	write(root / "intel-rapl:2/name", "psys"); // Whole-system domain is not CPU power.
	Collector collect(root);
	assert(collect.collect(1000).milliwatts == -1);
	write(zero / "energy_uj", "150000000"); write(one / "energy_uj", "270000000");
	assert(collect.collect(2000).milliwatts == 120000);
	write(one / "energy_uj", "invalid");
	assert(collect.collect(2500).milliwatts == -1); // No partial package total.
	write(one / "energy_uj", "300000000");
	assert(collect.collect(3000).milliwatts == -1); // Rebaseline after missing data.
	write(zero / "energy_uj", "200000000"); write(one / "energy_uj", "350000000");
	assert(collect.collect(4000).milliwatts == 100000);
	if (getuid() != 0) {
		fs::permissions(one / "energy_uj", fs::perms::none);
		const auto denied = collect.collect(4500);
		assert(denied.milliwatts == -1 and denied.status == "read access needed");
		fs::permissions(one / "energy_uj", fs::perms::owner_read | fs::perms::owner_write);
		assert(collect.collect(5000).milliwatts == -1);
	}
	collect.reset(); assert(collect.collect(6000).milliwatts == -1);
	fs::remove_all(one);
	write(zero / "energy_uj", "250000000");
	assert(collect.collect(7000).milliwatts == 50000);
	std::string unchanged; std::ifstream(zero / "enabled") >> unchanged; assert(unchanged == "0");
	bool denied = false; uint64_t value = 0;
	for (const auto* bad : {"", "-1", "+1", "5 junk", "NaN", "18446744073709551616"}) {
		write(root / "number", bad); assert(not number(root / "number", value, denied));
	}
	assert(Collector(root / "missing").collect(1).milliwatts == -1);
	assert(scale_mw({}, 10) == 50000);
	std::deque<Sample> history{{0, 125000, 0}, {10, 51000, 500}, {20, -1, 1000}};
	assert(scale_mw(history, 3) == 150000 and scale_mw(history, 2) == 100000 and scale_mw(history, 1) == 50000);
	std::cout << "Package-only totals, deduplication, energy/time conversion, wrap/reset/missing/permission handling, zero power and graph scale passed\n";
}
