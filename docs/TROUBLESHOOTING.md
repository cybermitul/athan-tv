# Troubleshooting

## No sound: `Playback open error: -2, No such file or directory`

The device address doesn't exist. Linux can swap sound-card numbers between boots (HDMI may be card 1 one day and card 0 the next), so numeric addresses like `plughw:1,3` break. Address the card by name instead, for example `hdmi:CARD=HDMI,DEV=0`. Confirm the names with `cat /proc/asound/cards` and `aplay -L`.

## No sound: `Write error: -5, Input/output error` on HDMI

The device opens, but the audio stream never reaches the TV. On Intel 4th-gen (Haswell) machines this is caused by the IOMMU (VT-d), which recent Debian kernels enable by default. It conflicts with Haswell's separate HDMI audio controller at PCI `00:03.0`. Signs: `dmesg | grep DMAR` shows `DMAR active`, and nothing is logged when playback fails.

Fix:

```bash
sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\)"/GRUB_CMDLINE_LINUX_DEFAULT="\1 intel_iommu=off"/' /etc/default/grub
update-grub      # required: editing /etc/default/grub alone does nothing
reboot
cat /proc/cmdline   # must now contain intel_iommu=off
```

Alternatively, re-run the installer with `DISABLE_IOMMU=yes`. The IOMMU only matters for VM device passthrough and protection against malicious hardware, neither of which applies to a kiosk.

If HDMI audio still fails, use the headphone jack into the TV's audio input or a small speaker: `ALSA_DEVICE="plughw:CARD=PCH,DEV=0"`.

## `atq` is empty

This is expected after Isha: the next batch is queued at 00:05. Check `tail /var/log/athan-schedule.log`. If fetches failed, the log shows retries. Run `/opt/athan/schedule-athan.sh` to queue now.

## Old adhan jobs still use a wrong device

`at` stores the full command when a job is queued. Jobs queued before a config change keep the old values. Re-run `/opt/athan/schedule-athan.sh`, which replaces its own jobs. Current jobs call `play-adhan.sh`, which reads `/etc/default/athan` at play time, so this only affects jobs from older versions.

## Page shows "Failed to fetch" or no prayer times

Check the box can reach the API:

```bash
curl -s "https://api.aladhan.com/v1/timings/$(date +%d-%m-%Y)?latitude=40.7128&longitude=-74.0060&method=2" | jq .data.timings
```

Previewing `index.html` inside a sandboxed viewer (for example a chat app's file preview) always fails, because those viewers block outside network requests. Test at `http://<box-ip>:8080` instead.

## TV shows a login screen or a black screen

```bash
systemctl status lightdm
cat /etc/lightdm/lightdm.conf.d/50-autologin.conf
ls -l ~youruser/.config/openbox/autostart
```

The autostart file must be in the **kiosk user's** home, not root's.

## Chromium offers to translate the page

The autostart passes `--disable-features=Translate`. If you launched Chromium some other way, add that flag.

## `sudo: command not found`

Debian's netinst doesn't install sudo when a root password is set. Use `su -`, or install it with `apt install sudo && usermod -aG sudo youruser`, then log in again.
