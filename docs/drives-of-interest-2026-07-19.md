# Drives of Interest — Email/Takeout Recovery (2026-07-19)

Physical-retrieval checklist for the WMS Strategy Correspondence effort
(COO `co-2xlv`, DataArchive `da-yc6` **Dock NASR Takeouts**, `da-za4`
**Coverage Ledger**). Ordered by priority.

---

## 1. NASR — the NAS rescue drive ★ PRIMARY TARGET

- **What it is:** 2 TB HDD (1863 GB), was in the Sabrent Dual SATA Bridge dock as **I:**
- **Identity:** SMART snapshot 2026-05-05 — healthy, 47,626 power-on hours; serial reads as zeros through the dock, so identify by size + label
- **Holds:** `I:\OldNAS\` — the complete ddrescue file-by-file rescue of the dead QNAP NAS (bead `da-xy2`, closed). Inside: `Backups/` (316 GB share) including **`GMailTakeouts/`** — the authoritative Google Takeout email repo (`takeout-20160307T134443Z.zip` + the `processed/` tree built 2026-03-20)
- **Status:** not docked; never harvested to staging; never cataloged (no manifest, no scan)
- **Action:** dock it → verify `OldNAS/Backups/GMailTakeouts/` → stage + hash + catalog scan → unblocks the email survey

## 2. W: — current harvest staging drive (dropped offline mid-session)

- **What it is:** the post-`4c39b6d` harvest staging root (F:→W: swap, bead `da-d2z`)
- **Holds:** staged per-drive copies — `Tera1A/`, `POCL/`, `DTJX/`, `RRTI/`, `DVRC/`, `WWYY/`, plus `ClaudeBackup/`, `DataArchive-exports/`, `_logs/`, `_tools/`
- **Status:** was mounted at `/mnt/w` earlier on 2026-07-19; went "No such device" mid-session — USB dock instability or unplugged
- **Note:** its `Tera1A/Files/oldLaptop Drive/` copy is an **empty shell** — the real oldLaptop content is on F:'s Tera1A copy (known harvest anomaly)
- **Action:** re-seat/remount; needed as staging destination when NASR is harvested

## 3. F: — older staging drive (currently mounted, working)

- **Holds:** `Tera1A/` (the copy with the real `oldLaptop Drive` content — source of the 7 Outlook PSTs extracted 2026-07-19), `DVRC/`, `WWYY/`, `C-4-26/`, `MYDESK/`, `DataArchive-exports/`
- **Status:** mounted at `/mnt/f`, healthy this session
- **Action:** none — just don't displace it from the dock while W:/NASR juggling happens

## 4. Tera1A — original 2006–2008 era archive drive

- **What it is:** 931 GB, Dual SATA Bridge dock, cataloged (2 scans, last 2026-03-24)
- **Holds (per catalog):** the `oldLaptop Drive` backup with the seven Outlook PSTs (~1.7 GB, 2002–2008 mail — already extracted to `DataArchive/data/pst-extract/`, ON HOLD per Steve 2026-07-19), and `My Documents\Messages\` — 3,383 GUID-named `.eml` files (Windows Live Mail/Outlook Express-style export, copied 2012-02-15)
- **Action:** only needed physically if the F: staged copy proves incomplete; the `.eml` Messages set is a possible secondary email source

## 5. POCL — the OCL-era SSD (2014–2018)

- **What it is:** 237 GB Samsung SSD 850 PRO ("The Professional Studio" in drive-stories), cataloged (scans through 2026-05-04)
- **Holds:** `source\repos` with **BankWebinars / BankWebinars5 / TTS / TTSCore / TTSWebJobs / CUMailer** canonical code; `OneDrive - OnCourse Learning`; `BankWebinars.git`; a 2018 `Outlook.pst` (0.3 MB stub)
- **Why it matters:** late-era WMS code + the OnCourse Learning trail; complements whatever the Takeout mail says about that period
- **Action:** none immediate — cataloged and staged; listed here because it's the code-side counterpart to the correspondence hunt

## 6. QNAP NAS (dead) — no action

- **What it was:** Z: / `\\192.168.0.11\Public`, 3.6 TB, "The Master Archive"
- **Status:** long dead; contents rescued to NASR (`da-xy2`). Listed only so nobody waits on it again — the enclosure/remaining disks have no pending role
- **Coverage note:** its FAILED catalog scan (scan 17) is the proving case for `da-za4` **Coverage Ledger**

---

*Written by COO 2026-07-19 during the Steve Capability Profile / WMS correspondence session. Update `da-yc6` when NASR is docked.*
