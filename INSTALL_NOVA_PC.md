# Install Nova btop on Nova PC

**[AI generated]** These instructions install the io19 Nova fork on an Ubuntu
Linux PC as your normal user. Build on Nova PC so the executable uses its own
system libraries. CPU count, mounts and network interfaces are discovered
locally; a working GPU driver supplies the GPU readings.

## 1. Prepare Nova PC

Close any running btop windows before installation or an upgrade, so an older
instance cannot save its previous settings over the new profile.

Install the build tools in a terminal on Nova PC:

```bash
sudo apt update
sudo apt install --no-install-recommends git build-essential python3 ca-certificates
```

The build needs a C++20 compiler (GCC 10.1+ or Clang 16+). GPU support is enabled
by the Linux Make build and loads monitoring libraries dynamically. For an
NVIDIA GPU, check that `nvidia-smi` already works as your normal user. These
instructions do not install or change GPU drivers.

## 2. Clone and build the current Nova branch

Use the public [GitHub repository](https://github.com/kuchida75/btop-nova), or
substitute the clone URL of your private Gitea mirror. The following commands
create a fresh source directory:

```bash
nova_repo_url="https://github.com/kuchida75/btop-nova.git"
nova_src="$HOME/src/Nova-btop-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$HOME/src"
git clone --branch nova/permanent-disk-throughput "$nova_repo_url" "$nova_src"
cd "$nova_src"
make -j2 THREADS=2 QUIET=true
./bin/btop --version
git rev-parse HEAD
```

The version should be `1.3.0-nova-io19` for this revision. Keep the printed
commit ID when reporting an issue. A fresh clone keeps any existing source
checkout and its local changes intact.

For an HTTPS certificate error, install/trust the Gitea server's CA certificate
on Nova PC, or use its configured SSH clone URL.

Preview the build using a separate profile inside this checkout:

```bash
sh ./launch-nova-btop
```

Check CPU readings, disk read/write rates, network, the full-width mounts table
and any detected GPU panel/processes. Press **q** to exit. Preview preferences
belong to the checkout; configure the installed view after the next step.

## 3. Back up and install the user command

Keep a copy of an existing user command and Nova profile:

```bash
nova_backup="$HOME/.local/share/btop-nova/manual-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$nova_backup"
if [ -f "$HOME/.bashrc" ]; then
    cp -a "$HOME/.bashrc" "$nova_backup/bashrc"
fi
if [ -e "$HOME/.local/bin/btop" ] || [ -L "$HOME/.local/bin/btop" ]; then
    cp -a "$HOME/.local/bin/btop" "$nova_backup/btop"
fi
if [ -d "$HOME/.local/share/btop-nova/config" ]; then
    cp -a "$HOME/.local/share/btop-nova/config" "$nova_backup/config"
fi
```

From the newly built checkout, install and apply the Nova palette:

```bash
python3 install_nova.py --apply-theme
~/.local/bin/btop --version
~/.local/bin/btop
```

Run the installer **without sudo**. It creates the isolated user command,
keeps versioned binaries, backs up the profile before applying the palette,
and preserves existing display preferences. It manages a marked Bash alias;
open a new Bash terminal to use `btop`. Other shells can invoke
`~/.local/bin/btop` directly.

If the installer finds an unrelated command or an unmanaged `btop` alias, it
stops and preserves it. Check `type -a btop` and keep its backup before resolving
that conflict. The system/snap installation and `~/.config/btop` are preserved.

Installed locations:

| Item | Location |
| --- | --- |
| User command | `~/.local/bin/btop` |
| Nova profile | `~/.local/share/btop-nova/config/btop/btop.conf` |
| Versioned executables | `~/.local/share/btop-nova/releases/` |
| Installer backups | `~/.local/share/btop-nova/backups/` |

## 4. Select the CPU layout

In **Options → CPU**, set:

| Setting | Value | Result |
| --- | --- | --- |
| `show_core_freq` | `True` | Per-logical-CPU MHz in up to three columns |
| `cpu_single_graph` | `True` | One upward CPU usage graph |
| `cpu_invert_lower` | `False` | No inverted lower graph if it is enabled later |
| `show_cpu_power` | `False` initially | Optional watts require readable energy counters |

**Shift+F** toggles per-thread MHz. The Nova layout keeps GPU height and gives
spare CPU rows back to network and processes. On 32 logical CPUs the MHz panel
needs 17 rows and, with temperatures, at least 87 terminal columns. Other CPU
counts get the rows they need. Small windows fall back automatically and
restore the readings when enlarged.

Use **F1**, **?**, **h**, or the **keys** button for the full keyboard reference
(**Shift+H** in Vim mode). **PgUp/PgDn** browse its pages; **Esc** returns.
**Shift+N**, **Shift+U**, **Shift+M** and **Shift+Z** control GPU histories,
GPU processes, mounts and zram. Zram stays hidden while unused.

## 5. Use Wi-Fi as the default network display

Identify the local wireless adapters:

```bash
for nova_iface in /sys/class/net/*; do
    if [ -d "$nova_iface/wireless" ] || [ -e "$nova_iface/phy80211" ]; then
        printf '%s: ' "${nova_iface##*/}"
        cat "$nova_iface/operstate"
    fi
done
```

In **Options → NET → `net_iface`**, enter the connected wireless interface's
exact name. Quit and reopen btop, then confirm that name appears in the network
panel title. The saved setting selects the interface shown at startup;
**b/n** can cycle interfaces during a session. Interface names are discovered
on each PC; the release defaults keep `net_iface=""` for automatic selection.

If editing the profile file directly, close all btop instances first. A running
instance can otherwise save its cached preferences over an external edit.

## 6. Optional live CPU watts

**Options → CPU → `show_cpu_power=True`** adds CPU package watts and a matching
trace beside CPU usage in one upward graph. Usage has a 0–100% scale; power
has its own labelled watt scale. This is package energy averaged over each
refresh interval, not whole-PC or wall-socket power.

The **CPU** and **PKG** legends identify the two differently coloured traces.
Their colours follow the selected theme. Power mode uses one upward chart and
keeps the three-column MHz readings alongside it.

Linux RAPL counters must be present and readable. Run the permission step on
the PC whose wattage you want to view. If that PC exposes counters but
restricts access, an administrator can grant your primary group read access
to the **package energy counters only**. This optional example covers the RAPL
paths used by the collector and skips core/subdomain/system energy counters:

```bash
nova_power_group=$(id -gn)
for nova_zone in /sys/class/powercap/intel-rapl:* \
                 /sys/class/powercap/intel-rapl/intel-rapl:* \
                 /sys/class/powercap/amd-rapl:* \
                 /sys/class/powercap/amd-rapl/amd-rapl:*; do
    [ -r "$nova_zone/name" ] || continue
    case "$(cat "$nova_zone/name")" in
        package-*)
            sudo chgrp "$nova_power_group" "$nova_zone/energy_uj"
            sudo chmod g+r "$nova_zone/energy_uj"
            ;;
    esac
done
```

Then enable the option and wait for two refreshes. `--W` means the reading is
unavailable; missing samples leave gaps. If no compatible package counters
exist, leave watts off. These permission changes usually expire at reboot.
No privileged helper, service, power-limit change or driver change is installed;
continue to run btop as your normal user.

### Keep CPU watts working after reboot

The optional helper prepares a group-specific udev rule. It matches RAPL CPU
package devices when they appear after boot or a driver reload, granting the
selected group read access to `energy_uj`. btop continues to run as your normal
user. This setup needs `udevadm verify` (systemd 254+) and was checked with
systemd 259 on Ubuntu 26.04.1.

Run these from the source checkout or portable archive on **each target PC**:

```bash
python3 prepare_cpu_power_access.py --output "$HOME/Downloads/nova-btop-cpu-power-access"
cat "$HOME/Downloads/nova-btop-cpu-power-access/99-nova-btop-cpu-power.rules"
cat "$HOME/Downloads/nova-btop-cpu-power-access/install.sh"
sudo sh "$HOME/Downloads/nova-btop-cpu-power-access/install.sh"
```

For the Debian package, the helper is also installed at
`/usr/share/doc/btop-nova/prepare_cpu_power_access.py`.

The administrator installer verifies the prepared rule's checksum and syntax,
installs it atomically as
`/etc/udev/rules.d/99-nova-btop-cpu-power.rules`, reloads udev rules and tests
access restoration by recreating boot-time counter permissions and replaying
the device event. Wait for **PASS**. This test briefly changes only the energy
file's access permissions; it does not reset energy or alter CPU power limits.
It restores current read access if the test fails. Existing unmanaged rules
are preserved; an earlier managed rule is backed up before replacement.

The rule persists across reboots. Keep `show_cpu_power=True` in btop. To remove
this optional persistence later:

```bash
sudo rm /etc/udev/rules.d/99-nova-btop-cpu-power.rules
sudo udevadm control --reload-rules
```

Current counter permissions last until reboot or driver reload after removal.
See the [udev documentation](https://www.freedesktop.org/software/systemd/man/latest/udev.html)
for device-event rule behavior.

## Updates and rollback

For an update, quit btop, repeat the fresh-clone/build/preview steps and rerun
`python3 install_nova.py` from that new checkout. Existing settings and older
versioned executables are retained. Use `--apply-theme` again only when you want
to reselect the Nova palette. Keep your original source checkout if it contains
local changes.

To remove only the Nova user command and marked Bash alias:

```bash
python3 rollback_nova.py
```

Open a new Bash terminal afterward. Releases, profiles and backups are kept;
any system/snap btop remains available through its original command. To restore
a previous Nova installation, quit btop and restore the saved launcher and
profile from your manual backup; keep the older release it references.

See [README_NOVA.md](README_NOVA.md) for packaging and controls, and
[NOVA.txt](NOVA.txt) for feature behavior and validation.
