# Family calendar and lists (Radicale on Unraid + iPhone)

The TV shows two extra slides after the Ayah and Hadith: **This Week** (the shared family calendar) and **Lists** (for example Groceries and To-Do). Both come from [Radicale](https://radicale.org), a small self-hosted CalDAV server. iPhones connect with the built-in Calendar and Reminders apps, so nobody installs anything.

```
iPhones (Calendar, Reminders) --read/write, user "family"--> Radicale :5232 on Unraid
athan-tv  fetch-family.py     --read-only, user "tv"------> Radicale :5232 on Unraid
```

Everyone's phone uses one shared `family` account; the TV uses a separate `tv` account that the rights file limits to **read-only** access to the family's collections. A compromised kiosk can't change or delete anything.

## 1. Create the passwords (Mac)

```bash
openssl rand -base64 18        # -> TV password (long, random; nobody types it by hand)
cd ~/Projects/athan-tv/server/radicale
htpasswd -cB users family      # choose a family password you'll enter on each iPhone
htpasswd -B  users tv          # paste the TV password from above
```

`-B` stores bcrypt hashes; `-c` creates the file (only on the first command). The `users` file holds hashes, never plain passwords, and is git-ignored.

## 2. Radicale on Unraid

Copy the config to Unraid:

```bash
ssh root@192.168.1.3 'mkdir -p /mnt/user/appdata/radicale/config /mnt/user/appdata/radicale/data'
scp config rights users root@192.168.1.3:/mnt/user/appdata/radicale/config/
```

Unraid web UI → **Docker** → **Add Container**:

| Field | Value |
|---|---|
| Name | `radicale` |
| Repository | `tomsquest/docker-radicale` |
| Network Type | `Bridge` |
| Extra Parameters | `--init --read-only --security-opt=no-new-privileges:true --cap-drop=ALL --cap-add=SETUID --cap-add=SETGID --cap-add=CHOWN --cap-add=KILL` |

Then **Add another Path, Port, Variable, Label or Device** three times:

| Config Type | Container | Host | Access |
|---|---|---|---|
| Port | `5232` | `5232` | TCP |
| Path | `/data` | `/mnt/user/appdata/radicale/data` | Read/Write |
| Path | `/config` | `/mnt/user/appdata/radicale/config` | Read Only |

Click **Apply**. Check it from the Mac (enter the family password when asked):

```bash
curl -u family -s -o /dev/null -w "%{http_code}\n" -X PROPFIND -H "Depth: 1" http://192.168.1.3:5232/family/
```

`207` means it works. `401` means the user or password is wrong.

## 3. iPhone (each family member)

1. **Settings → Apps → Calendar → Calendar Accounts → Add Account → Other → Add CalDAV Account** (iOS 17 and earlier: Settings → Calendar → Accounts → Add Account → Other).
2. Server `192.168.1.3:5232`, User Name `family`, the family password, Description `Family`. Tap **Next**.
3. iOS says it cannot connect using SSL; tap **Continue** to set up without it.
4. Keep **Calendars** and **Reminders** switched on. Save.
5. On the **first** phone only, create the shared collections:
   - Calendar app → **Calendars** → **Add Calendar** → account **Family** → name `Family`.
   - Reminders app → **Add List** → account **Family** → `Groceries`, then again for `To-Do`.
6. Optional: Settings → Apps → Calendar → **Default Calendar** → Family, so new events go to the shared calendar.

Changes from a phone reach the server immediately and the TV within 5 minutes. Other phones pick them up on their next fetch (Settings → Apps → Mail → Mail Accounts → Fetch New Data → every 15 minutes).

**Away from home**, phones can't reach Radicale unless they're on the home VPN (WireGuard on the UDR7). Changes made outside queue on the phone and sync when you're back. Don't publish Radicale to the internet.

## 4. Firewall: let the TV reach Radicale

The TV box is on the IoT VLAN (192.168.30.163) and Unraid is on Default (192.168.1.3). In UniFi Network, allow only that one flow:

- **Zone-based firewall** (Network 9+): Settings → Policy Engine → Zones / Policy Table → **Create Policy**
  - Source: zone that contains the IoT network, IP `192.168.30.163`
  - Destination: zone that contains Default, IP `192.168.1.3`, port `5232`, protocol TCP
  - Action: **Allow**
- **Classic rules** (older firmware): Settings → Security → Traffic & Firewall Rules → Create Entry → Type **LAN In**, Action **Accept**, TCP, source `192.168.30.163`, destination `192.168.1.3` port `5232`, placed above any IoT → Default block rule.

Give athan-tv a fixed DHCP reservation (Client Devices → athan-tv → Settings → Fixed IP Address) so the rule stays valid.

## 5. Point the TV at Radicale

On the box as root:

```bash
curl -u tv -s -o /dev/null -w "%{http_code}\n" -X PROPFIND -H "Depth: 1" http://192.168.1.3:5232/family/
```

`207` confirms the firewall rule and the tv account. Then set the four values in `/etc/default/athan` (append the block from `athan.conf.example` if it's missing):

```bash
nano /etc/default/athan     # FAMILY=true, CALDAV_URL, CALDAV_USER=tv, CALDAV_PASS
/opt/athan/apply-config.sh
/opt/athan/fetch-family.py
systemctl restart lightdm
```

`fetch-family.py` prints something like `5 event(s) in the next 7 days; lists: Groceries (8), To-Do (3)`.

## Notes

- **Lists on the TV** show unchecked items only. High-priority reminders get an amber box and sort first; due dates show as Today, Overdue, or the date.
- **Which lists**: `FAMILY_LISTS="Groceries, To-Do"` picks lists by name and order. Leave it empty to show every list.
- **Empty slides are skipped**: no events this week means no week slide; no lists means no lists slide.
- **Plain HTTP**: passwords cross the LAN unencrypted (HTTP Basic auth). Acceptable on a trusted home LAN; to add TLS later, put Radicale behind your reverse proxy and change the iPhone and `CALDAV_URL` settings to `https`.
- **Backups**: everything lives in `/mnt/user/appdata/radicale/data` as plain `.ics` files, covered by your appdata backup.
