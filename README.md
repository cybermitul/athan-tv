# athan-tv

A self-hosted prayer-times display for a living-room TV. An old mini PC runs Debian in kiosk mode, shows the day's prayer times over rotating masjid photography with an hourly Quran ayah and hadith, and plays the adhan through the TV speakers at each of the five prayers.

Everything runs locally except three free, keyless APIs: [Aladhan](https://aladhan.com/prayer-times-api) for prayer times, [alquran.cloud](https://alquran.cloud/api) for the Quran, and [fawazahmed0/hadith-api](https://github.com/fawazahmed0/hadith-api) for hadith. The page caches the last good data, so a network outage never leaves the TV blank.

## Features

- Live clock, Gregorian date, and Hijri date in Arabic and English
- Fajr, Sunrise, Dhuhr, Asr, Maghrib, Isha with the current prayer highlighted; Dhuhr becomes Jumu'ah on Fridays
- Next-prayer countdown that pulses gold in the final 10 minutes
- Ayah of the Hour and Hadith of the Hour (Sahih al-Bukhari / Sahih Muslim) in Arabic, with English, Urdu, and Bengali translations rotating underneath; text auto-sizes to fit
- Background photos that crossfade every 10 minutes
- Adhan at all five prayers via `at` jobs queued nightly by cron, with an optional separate recording and volume for Fajr
- Survives reboots and power cuts: auto-login, auto-launch, Chromium crash-bar suppression, network retry

## How it works

```
cron 00:05 / @reboot ──► schedule-athan.sh ──► Aladhan API
                               │
                               └─► at HH:MM ──► play-adhan.sh ──► mpg123 ──► ALSA ──► HDMI ──► TV speakers

LightDM autologin ──► Openbox ──► Chromium --kiosk ──► http://localhost:8080
                                                         │
                                          nginx (Docker) serves /opt/athan/web
                                                         │
                                  index.html ──► Aladhan / alquran.cloud / hadith-api
```

Audio is deliberately decoupled from the browser. The adhan is played by the OS scheduler rather than the web page, so it still plays if Chromium crashes, and browser autoplay rules never get in the way.

`/etc/default/athan` is the single source of truth for location, calculation method, languages, and audio device. `apply-config.sh` renders it into `web/config.js` for the page, and the scheduler reads it directly, so the displayed times and the adhan times always come from the same settings.

## Hardware

Tested on a Lenovo ThinkCentre Tiny with an Intel Core i5 4th gen (Haswell), 8 GB DDR3, and an HDD, connected to a 32" Insignia TV through a DisplayPort-to-HDMI adapter. Almost any x86-64 box with video out will work.

## Install

1. Install **Debian 13 (Trixie)** from the netinst ISO. At *Software selection*, untick every desktop environment and keep only **SSH server** and **standard system utilities**.
2. Log in as root (`su -`) and get the code:
   ```bash
   apt install -y git
   git clone https://github.com/<your-username>/athan-tv.git
   cd athan-tv
   ```
3. Run the installer with your kiosk user and coordinates:
   ```bash
   KIOSK_USER=youruser LATITUDE=40.7128 LONGITUDE=-74.0060 ./scripts/install.sh
   ```
   Add `DISABLE_IOMMU=yes` on 4th-gen Intel hardware if HDMI audio is silent (see [Troubleshooting](docs/TROUBLESHOOTING.md)).
4. Set your audio device in `/etc/default/athan` (see below), then test and reboot:
   ```bash
   /opt/athan/play-adhan.sh test
   reboot
   ```

The installer is idempotent. Re-running it after a `git pull` updates the page and scripts while keeping your `/etc/default/athan`, photos, and audio.

## Configuration

Edit `/etc/default/athan`, then apply:

```bash
/opt/athan/apply-config.sh && systemctl restart lightdm
```

| Setting | Meaning |
|---|---|
| `LATITUDE`, `LONGITUDE` | Your location |
| `METHOD` | Calculation method: 2 = ISNA, 3 = MWL, 4 = Umm al-Qura, 5 = Egyptian ([full list](https://aladhan.com/prayer-times-api)) |
| `SCHOOL` | 0 = standard Asr, 1 = Hanafi Asr |
| `TUNE` | Optional per-prayer minute offsets |
| `TRANSLATION_LANGS` | Any of `en ur bn`; Arabic is always shown |
| `ALSA_DEVICE` | Audio output (see below) |
| `SCALE`, `FAJR_SCALE` | mpg123 volume scale, where 32768 = 100%. For example, `FAJR_SCALE=13000` makes Fajr about 40% volume |
| `FAJR_AUDIO` | Separate Fajr recording, used if the file exists |

**Finding the audio device.** The HDMI port connected to the TV reports the TV's model name:

```bash
grep -H "monitor_present\|monitor_name" /proc/asound/card*/eld*
aplay -L | grep -A1 '^hdmi'
```

Use the `hdmi:CARD=HDMI,DEV=N` entry that lists your TV, or `plughw:CARD=PCH,DEV=0` for the headphone jack. Address cards by name, not number, because card numbers can swap between boots.

**Background photos.** Drop any JPEGs into `/opt/athan/web/bg/` named `1.jpg` through `10.jpg`. Missing numbers are skipped. `fetch-media.sh` fills slots 1–5 with Wikimedia Commons photos and never overwrites an existing file.

## Useful commands

```bash
atq                                      # today's queued adhan jobs
tail -20 /var/log/athan-schedule.log     # scheduler and playback log
/opt/athan/play-adhan.sh test            # play the adhan now
/opt/athan/schedule-athan.sh             # re-queue today's prayers
docker compose -f /opt/athan/docker-compose.yml ps
systemctl restart lightdm                # restart the kiosk display
```

## Repository layout

```
web/index.html            the dashboard (single file, no build step)
scripts/install.sh        end-to-end installer
scripts/schedule-athan.sh fetches times, queues at jobs
scripts/play-adhan.sh     plays the adhan (per-prayer file and volume)
scripts/apply-config.sh   /etc/default/athan -> web/config.js
scripts/fetch-media.sh    downloads backgrounds and adhan
config/                   Openbox autostart, LightDM autologin, logrotate
athan.conf.example        template for /etc/default/athan
docker-compose.yml        nginx:alpine serving web/ on :8080
docs/                     troubleshooting and media credits
```

## Credits

Prayer times: Aladhan. Quran text and translations: alquran.cloud (Uthmani script; Sahih International; Fateh Muhammad Jalandhry; Muhiuddin Khan). Hadith: fawazahmed0/hadith-api. Photos and adhan recording: Wikimedia Commons contributors; see [docs/CREDITS.md](docs/CREDITS.md).

## License

Code is MIT licensed (see [LICENSE](LICENSE)). Downloaded media keeps its own license, listed in [docs/CREDITS.md](docs/CREDITS.md).
