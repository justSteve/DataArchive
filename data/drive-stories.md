# Drive Stories

A narrative catalog of every drive that passes through the archive.

---

## UIER — The First Workshop (2003–2014)

**Hardware:** 84GB drive, USB via Sabrent dock
**Scanned:** 2026-03-23, scan 15 — 109,518 files, 33.5 GB
**Era:** August 2003 – November 2014

This is the earliest development drive we've found so far. It's not a boot drive — it's a pure data partition with four top-level folders: Documents, Projects, vmBackups, and archive_db.

The heart of it is **Documents/Visual Studio 2012** — nearly 99,000 files. This was Steve's primary development environment during the VS2012 era. There's also VS2010 and VS2013 content, showing the progression. GitHub repos (4,815 files) suggest this is the period when Steve started using source control beyond local projects.

**Documents/IISExpress** (1,668 files) tells us these were web applications running locally. The extension breakdown confirms it: heavy on .cs (C#), .js, .cshtml (Razor views), .css, .png, .jpg — classic ASP.NET MVC web development.

**Projects/** has OfficeApps (1,588 files), FileUploader, and an AzureImporter — early experiments with Office integration and cloud migration.

The **vmBackups** folder holds 7 files totaling 18.9 GB — full virtual machine snapshots, probably of dev environments or client systems.

Other traces: Google Data API SDK, My Kindle Content, Camtasia Studio (screen recording — maybe for training/webinar content?), RoboForm data, QNAP NAS navigator, SQL Server Management Studio, a Firefox extension backup (FEBE).

**Story:** This drive is the workbench from Steve's ASP.NET web development years. The code that would eventually become bankwebinars.com and ttstrain.com was being written here. The Camtasia Studio presence hints at webinar content creation — the business wasn't just building the platform, it was using it.

---

## OCL — The Professional Studio (2014–2018)

**Hardware:** 237GB SSD, USB via Sabrent dock
**Scanned:** 2026-03-23, scan 16 — 250,087 files, 58.9 GB
**OS:** Windows 10 Pro, build 17134, installed 2018-05-28
**SMART:** 19,150 power-on hours (~2.2 years continuous)
**Era:** Files from 1999 (carried-forward tools) through June 2018

This is UIER's successor — the machine Steve upgraded to when the business matured. Where UIER had VS2012, OCL runs VS2013/2015/2017. The full .NET stack is here: SQL Server 2016 (with SSAS, SSIS, the works), Entity Framework, .NET Core SDK 1.0/1.1, Docker, Azure tooling.

**445 installed applications**, 262 of which are development tools. This machine was purpose-built for work.

The `source\repos` folder is the canonical code from this era:
- **BankWebinars** and **BankWebinars5** — the bankwebinars.com platform, actively developed through March–April 2018
- **TTS**, **TTSCore**, **TTSWebJobs** — the ttstrain.com platform and its background processing
- **CUMailer** (3 versions) — cuwebinars.com email system
- **Common**, **DLLs**, **ConfigAssignUtility**, **MailChimp**, **WebJobConfigs** — shared infrastructure

OneDrive/Code holds backup copies and supplementary projects: SQL queries, API projects, a GitHub-ready version of TTS, utilities. The SQL folder has queries dated through June 2018 with names like `FindUnInvoicedOrders.sql` and `Series5_CallRpt` — this was active business operations.

**Personal traces on this machine:** Garmin HomePort + GPSInfo (boating/navigation), boat photos on the desktop (MyBoatTransom.jpg, proposedmotormount.png), OpenCPN chart plotter, SAT2CHART nautical software. Brother printer. 32GB of photos organized by month (2014-11 through 2018-01), plus a Canon camera folder and a Costa Rica/Belize trip. 10GB of music.

**Story:** OCL is the professional chapter. The business was fully operational — webinar platforms for banks and credit unions, training systems, mailing infrastructure. Steve was simultaneously maintaining a boat (motor mount project, charts, GPS) and traveling (Costa Rica/Belize). The RoboForm data from UIER carries forward, as do Sysinternals tools dating back to 1999 — some files follow you your whole career.

---

## DTJX — The Current Workstation (2019–present)

**Hardware:** WDC WD40EZRZ-00GXCB0, 2TB WD Blue, SATA direct to motherboard
**Serial:** WD-WCC7K7XHTP1L
**Scanned:** 2026-03-23, scan 13 — 518,396 files, 101.8 GB on 2TB
**OS:** Windows 10/11 (detected by pattern, registry locked from WSL)
**Era:** Files from 2019 through March 2026 (active)

This is the current machine. The 2TB WD Blue is a secondary partition (not the boot NVMe) holding the Windows install alongside the Samsung SSDs. 518K files but only 102GB of content on 2TB — the drive is mostly empty, with Windows, Program Files, and ProgramData accounting for nearly everything.

The installed software shows the evolution from OCL: SketchUp 2024/2026 with LayOut (3D design/fabrication), Docker + Hyper-V + Linux Containers (deeper into containerization), Obsidian (knowledge management replacing OneNote), Python presence (11K+ .py files — a shift from .NET-only), LINQPad, Moneydance, TradeStation (trading).

The Users/steve profile is permission-locked from WSL (this is the live system). The interesting personal content — documents, photos, projects — isn't in this scan. But the software footprint tells the story: the professional .NET developer has branched into 3D design, Python, trading, and is managing home infrastructure (Plex, QNAP, Docker).

SAT2CHART and OpenCPN are still installed. The boat endures.

**Story:** DTJX is where everything converges. It's not archival material — it's the living machine. But it tells us who Steve is *now*: a maker who codes in multiple languages, designs in 3D, trades markets, runs home infrastructure, and still keeps nautical charts close at hand. The progression from UIER → OCL → DTJX tracks a career arc from focused .NET web developer to polyglot technologist.

---

## LBWZ — The Production Server (2006–2018)

**Hardware:** 238GB, Sabrent dock (originally via SATA)
**Scanned:** 2026-03-09, scan 10 — 8,613 files, 5.2 GB
**Era:** July 2006 – December 2018

This isn't a workstation — it's a **production web server**. The scan only captured what WSL could read (8,613 files across ProgramData, inetpub, and Users), but the footprint tells the story clearly.

**inetpub/wwwroot** holds a single ASP.NET MVC application: Content, Scripts, Views, bin, App_Data, Membership, Notification infrastructure. This is a deployed web app — not source code, but the running site. The Views/Scripts/Content structure and packages.config point to an MVC4/5 era app. Given the timeline and Steve's business, this is likely a deployed instance of the TTS/webinar platform.

**The toolchain on this server:** Visual Studio 2010 and 2012 (via the Default user profile), Chocolatey package manager, Red Gate SQL tools, Adobe Camera Raw profiles (3,505 files — possibly for processing uploaded images), NVIDIA drivers, PreEmptive Solutions (Dotfuscator — code obfuscation for deployed .NET apps), LogMeIn Hamachi (VPN for remote access to this server).

**Hamachi is the tell.** This wasn't a cloud-hosted server — it was a physical machine Steve ran himself, accessible remotely via Hamachi VPN. A self-hosted production environment from the era before cheap cloud hosting was ubiquitous.

The `.dcp` and `.lcp` files (camera profiles) dominating the extension list are from Adobe — probably part of a content processing pipeline for webinar recordings or promotional materials.

**Story:** LBWZ is the server that ran the business. While UIER and OCL were where the code was written, LBWZ is where it was deployed. Self-hosted, remotely managed via Hamachi, running an ASP.NET MVC stack with SQL tooling. This is the production side of bankwebinars.com/ttstrain.com — the machine that actually served customers.

---

## TJDD — The Fast One (mid-2000s, unrecoverable so far)

**Hardware:** WD1500ADFD (WD Raptor), 150GB, 10,000 RPM, SATA
**Status:** Click of death on power-up, 2026-03-23. No data recovered.
**Recovery plan:** SpinRite session when ready.

A WD Raptor. These were the enthusiast performance drives of the mid-2000s — before SSDs, this was the fastest consumer storage you could buy. Whatever was on TJDD, it was important enough to put on the premium hardware. Given the timeline (UIER covers 2003–2014, OCL picks up at 2014), TJDD likely held the OS or primary workspace from the same era — possibly the boot drive that UIER was the data partition for.

The platters may still hold data. SpinRite is designed for exactly this situation.

---

## Drives Pending Full Stories

### New D: (298GB, currently scanning)
**First peek:** Contains `Code/`, `Images/`, `Backups/`, `Picasa Backup - All Moms Scanned Photos`, and several hash-named folders. Family archive material. Story to be written after scan completes.

### Z: — The Master Archive (QNAP NAS)
**Mount:** \\\\192.168.0.11\\Public, 3.6TB, 769GB used
**Baseline:** Backups (316GB), qnap (283GB), Shared Pictures (88GB), Shared Music (62GB), Shared Videos (11GB)
**Role:** Consolidation destination. Not a closet drive — the living archive. Scan in progress.

---

*Last updated: 2026-03-23*
