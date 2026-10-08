#include "../src/btop_mounts.hpp"
#include <cassert>
#include <iostream>
#include <sstream>

int main(int argc, char**) {
	if (argc > 1) {
		for (const auto& row : Mounts::collect())
			std::cout << row.mountpoint << '\t' << row.total << '\t' << row.used << '\t' << row.available << '\t' << row.fstype << '\t' << row.device << '\n';
		return 0;
	}
	std::istringstream sample(
		"1 0 8:1 / / rw - ext4 /dev/sda1 rw\n"
		"2 1 8:2 / /boot rw shared:1 - ext4 /dev/sda2 rw\n"
		"3 1 8:3 / /boot/efi rw - vfat /dev/sda3 rw\n"
		"4 1 8:4 / /mnt/My\\040Disk rw - ntfs3 /dev/sdb1 rw\n"
		"5 1 8:1 / /long/root-copy rw - ext4 /dev/sda1 rw\n"
		"6 1 8:1 /directory /mnt/bind rw - ext4 /dev/sda1 rw\n"
		"7 1 7:0 / /snap/app rw - squashfs /dev/loop0 ro\n"
		"8 1 0:1 / /run rw - tmpfs tmpfs rw\n"
		"9 1 0:2 / /mnt/network rw - nfs server:/share rw\n"
		"10 1 8:5 /@home /home rw - btrfs /dev/sdc1 rw\n"
		"11 1 8:5 /@ /btrfs rw - btrfs /dev/sdc1 rw\n"
		"12 1 0:3 / /pool rw - zfs tank rw\n"
		"a malformed line\n"
		"13 1 8:8 / /bad rw not-a-separator ext4 /dev/sdd1 rw\n");
	auto entries = Mounts::parse_mountinfo(sample);
	assert(entries.size() == 7);
	assert(entries.front().mountpoint == "/");
	assert(entries[5].mountpoint == "/mnt/My Disk");
	assert(Mounts::decode_field("one\\134two\\011tab\\012line") == "one\\two\ttab\nline");
	assert(Mounts::display_text("bad\x1b[31m\tname") == "bad?[31m?name");
	for (int width = 42; width <= 300; ++width) {
		for (int longest : {0, 17, 50, 1000}) {
			const auto cols = Mounts::columns(width, longest, longest);
			assert(cols.total() == width);
			assert(cols.mount >= 14 and cols.percent == 6);
			assert(cols.bar == 0 or cols.bar >= 4);
		}
	}
	assert(Mounts::format_bytes(0, false, 5) == "0B");
	assert(Mounts::format_bytes(1024, false, 5) == "1.0K");
	assert(Mounts::format_bytes(1000, true, 5) == "1.0K");
	assert(Mounts::format_bytes(987221864448, false, 6) == "919.4G");
	assert(Mounts::format_bytes(987221864448, false, 5) == "919G");
	assert(Mounts::columns(82, 17, 33).device > 0);
	assert(Mounts::columns(60, 17, 33).type > 0);
	assert(Mounts::columns(42, 17, 33).type == 0);
	for (int height = 16; height <= 150; ++height) {
		for (bool detailed : {false, true}) {
			for (int count : {0, 1, 5, 50, 1000}) {
				const auto reserved = Mounts::table_height(height, 84, count, detailed, true);
				assert(reserved == 0 or reserved >= 5);
				assert(height - (detailed ? 8 : 0) - reserved >= 13 or reserved == 0);
				assert(reserved <= (height - (detailed ? 8 : 0))/3);
			}
		}
	}
	assert(Mounts::table_height(16, 44, 5, false, true) == 0);
	assert(Mounts::table_height(50, 84, 5, false, true) == 9);
	assert(Mounts::table_height(50, 84, 5, false, false) == 0);
	std::cout << "Mount parsing, deduplication, escaped names, column bounds and process-space limits passed\n";
}
