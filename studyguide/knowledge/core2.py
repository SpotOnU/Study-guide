"""A small, hand-checked bank of CompTIA A+ Core 2 concepts.

This is *added context*, not slide content. The generator only uses an entry
when one of your slides mentions the concept, and the app always labels these
questions as "Added CompTIA A+ Core 2 context" so it is clear the explanation
did not come from your slide.

Each entry has one clear, self-contained question, the correct answer, an
explanation of why it is correct, and plausible alternatives with a short
reason why each is wrong.

Matching rules:
* ``aliases`` are specific terms (e.g. "BitLocker"): a mention anywhere on a
  slide counts.
* ``generic_aliases`` are everyday words (e.g. "application"): they only count
  when they appear in the slide title or at least twice on the slide, so an
  unrelated slide that happens to use the word doesn't get this question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

SOURCE_LABEL = "Added CompTIA A+ Core 2 context"


@dataclass(frozen=True)
class Concept:
    key: str
    term: str
    question: str
    answer: str
    explanation: str
    confusers: Tuple[Tuple[str, str], ...]
    aliases: Tuple[str, ...] = ()
    generic_aliases: Tuple[str, ...] = ()
    case_sensitive: Tuple[str, ...] = field(default=())  # aliases that must match case (e.g. "su")


def c(key, term, question, answer, explanation, confusers, aliases=(), generic=(), case_sensitive=()):
    return Concept(key, term, question, answer, explanation, tuple(confusers), tuple(aliases),
                   tuple(generic), tuple(case_sensitive))


CONCEPTS: List[Concept] = [
    # ---------------------------------------------------------------- software
    c("app-software", "Application software",
      "Which type of software lets a user perform a specific task, such as editing a document?",
      "Application software",
      "Application software is built for end-user tasks such as word processing, web browsing or email. "
      "It runs on top of the operating system, which manages the hardware and provides services that "
      "applications rely on.",
      [("Operating system", "The operating system manages hardware and resources and provides services "
                            "to applications; it is not built for one specific user task."),
       ("Device driver", "A driver lets the operating system communicate with a specific hardware device."),
       ("Firmware (BIOS/UEFI)", "Firmware is low-level code stored on the hardware that starts the system "
                                "before the operating system loads.")],
      aliases=["application software"], generic=["application", "applications", "app", "apps"]),
    c("os", "Operating system",
      "Which software manages a computer's hardware resources and provides the services that applications run on?",
      "The operating system",
      "The operating system (such as Windows, macOS or Linux) controls the CPU, memory, storage and devices, "
      "and gives applications a consistent way to use them.",
      [("Application software", "Applications perform user tasks and depend on the operating system; they "
                                "don't manage the hardware themselves."),
       ("Device driver", "A driver is a small component the operating system uses to talk to one device."),
       ("Hypervisor", "A hypervisor creates and runs virtual machines, each of which runs its own "
                      "operating system.")],
      aliases=["operating system", "operating systems"]),
    c("sys-req", "System requirements",
      "Before installing an application, what should you compare with the computer's CPU, RAM, free storage "
      "and OS version to confirm the application will run?",
      "The application's system requirements",
      "System requirements list the minimum (and recommended) hardware and operating system an application "
      "needs. Checking them before installing avoids failed installs and poor performance.",
      [("The software license agreement", "A license covers the legal terms of use, not whether the hardware "
                                           "can run the software."),
       ("The installation log", "An installation log records what happened during an install, after the fact."),
       ("The installer's file hash", "A hash verifies the download wasn't altered; it says nothing about "
                                     "hardware compatibility.")],
      aliases=["system requirements", "minimum requirements", "hardware requirements"]),
    c("32bit-ram", "32-bit memory limit",
      "What is the maximum amount of RAM a 32-bit operating system can address?",
      "4 GB",
      "A 32-bit system uses 32-bit memory addresses, and 2³² addresses is 4 GB. A 64-bit operating "
      "system can address far more memory, which is one reason 64-bit is now standard.",
      [("16 GB", "16 GB is more than 32 address bits can reference; it needs a 64-bit OS."),
       ("128 GB", "128 GB is only possible with a 64-bit operating system."),
       ("2 TB", "2 TB is far beyond the 4 GB a 32-bit address space can reach.")],
      generic=["32-bit", "x86", "32 bit"]),
    # ------------------------------------------------------------ file systems
    c("ntfs", "NTFS",
      "Which Windows file system supports file and folder permissions, encryption with EFS and very large files?",
      "NTFS",
      "NTFS (NT File System) is the standard Windows file system. It adds security permissions, EFS "
      "encryption, journaling and support for very large files and volumes.",
      [("FAT32", "FAT32 has no file permissions and limits individual files to 4 GB."),
       ("exFAT", "exFAT is designed for removable flash storage and lacks NTFS permissions and EFS."),
       ("ext4", "ext4 is a Linux file system, not the standard Windows one.")],
      aliases=["NTFS"]),
    c("fat32", "FAT32",
      "Which widely compatible file system limits individual files to a maximum of 4 GB?",
      "FAT32",
      "FAT32 works with almost every operating system and device, but a single file on it can be at most "
      "4 GB, which rules it out for large video files and disk images.",
      [("NTFS", "NTFS supports files far larger than 4 GB."),
       ("exFAT", "exFAT was designed to remove FAT32's 4 GB file limit."),
       ("APFS", "APFS is Apple's modern file system and supports very large files.")],
      aliases=["FAT32", "FAT 32"]),
    c("exfat", "exFAT",
      "Which file system is designed for removable flash storage, supports files larger than 4 GB, and can be "
      "read and written by both Windows and macOS?",
      "exFAT",
      "exFAT (Extended FAT) is a lightweight file system for USB drives and memory cards. It removes FAT32's "
      "4 GB file limit and is supported for reading and writing by both Windows and macOS.",
      [("FAT32", "FAT32 is widely compatible but limits files to 4 GB."),
       ("NTFS", "macOS can read NTFS but cannot write to it without extra software."),
       ("ext4", "ext4 is a Linux file system that Windows and macOS don't support natively.")],
      aliases=["exFAT"]),
    c("ext4", "ext4",
      "Which file system is the common default on Linux distributions?",
      "ext4",
      "ext4 (fourth extended file system) is the default file system on many Linux distributions. It is "
      "journaled and supports large files and volumes.",
      [("NTFS", "NTFS is the standard Windows file system."),
       ("APFS", "APFS is the default file system on modern macOS."),
       ("FAT32", "FAT32 is an older, widely compatible file system with a 4 GB file limit.")],
      aliases=["ext4", "ext3"]),
    c("apfs", "APFS",
      "Which file system is the default on modern versions of macOS?",
      "APFS (Apple File System)",
      "APFS replaced the older HFS+ as the macOS default. It is optimized for SSDs and supports features such "
      "as snapshots and built-in encryption.",
      [("HFS+", "HFS+ (Mac OS Extended) is the older macOS file system that APFS replaced."),
       ("NTFS", "NTFS is the Windows file system; macOS can read it but not write to it natively."),
       ("ext4", "ext4 is the common Linux file system.")],
      aliases=["APFS", "Apple File System"]),
    # -------------------------------------------------------------- encryption
    c("bitlocker", "BitLocker",
      "Which Windows feature encrypts an entire storage volume to protect data if a drive is lost or stolen?",
      "BitLocker",
      "BitLocker provides full-volume encryption, so data on the drive can't be read without the key even "
      "if the drive is removed from the computer.",
      [("EFS", "EFS encrypts individual files and folders, not the entire volume."),
       ("User Account Control (UAC)", "UAC prompts before changes that need administrator rights; it doesn't "
                                      "encrypt data."),
       ("Windows Defender Firewall", "The firewall filters network traffic; it doesn't encrypt stored data.")],
      aliases=["BitLocker", "BitLocker To Go"]),
    c("efs", "EFS",
      "Which NTFS feature encrypts individual files and folders so only the user account that encrypted them "
      "can open them?",
      "EFS (Encrypting File System)",
      "EFS encrypts chosen files and folders on an NTFS volume, tied to the user's account and certificate. "
      "Other users on the same computer can't open them.",
      [("BitLocker", "BitLocker encrypts the whole volume, not individual files for one user."),
       ("FileVault", "FileVault is macOS full-disk encryption."),
       ("NTFS permissions", "Permissions control access, but the data itself is not encrypted.")],
      aliases=["EFS", "Encrypting File System"]),
    c("filevault", "FileVault",
      "Which macOS feature provides full-disk encryption?",
      "FileVault",
      "FileVault encrypts the startup disk on a Mac, so the data can't be read without the user's password or "
      "recovery key.",
      [("Time Machine", "Time Machine is the macOS backup tool."),
       ("Keychain", "Keychain securely stores passwords, keys and certificates; it doesn't encrypt the disk."),
       ("Spotlight", "Spotlight is the macOS search feature.")],
      aliases=["FileVault"]),
    # ------------------------------------------------------------------- macOS
    c("time-machine", "Time Machine",
      "Which built-in macOS tool makes automatic, incremental backups?",
      "Time Machine",
      "Time Machine automatically backs up a Mac to an external or network drive, keeping hourly, daily and "
      "weekly versions so you can restore individual files or the whole system.",
      [("FileVault", "FileVault encrypts the disk; it doesn't back it up."),
       ("Disk Utility", "Disk Utility manages disks and partitions and runs First Aid repairs."),
       ("Keychain", "Keychain stores passwords and certificates.")],
      aliases=["Time Machine"]),
    # ---------------------------------------------------------------- Windows
    c("uac", "User Account Control",
      "Which Windows feature asks for permission or administrator credentials before a change that needs "
      "elevated rights?",
      "User Account Control (UAC)",
      "UAC runs programs with standard rights by default and shows a prompt when something needs "
      "administrator access. This helps stop malware or mistakes from making system-wide changes silently.",
      [("BitLocker", "BitLocker encrypts drives; it doesn't control elevation prompts."),
       ("Windows Defender Firewall", "The firewall filters network traffic."),
       ("Group Policy", "Group Policy centrally configures settings; it isn't the per-action elevation prompt.")],
      aliases=["UAC", "User Account Control"]),
    c("task-manager", "Task Manager",
      "Which Windows tool shows running processes and performance, and lets you end a program that has stopped "
      "responding?",
      "Task Manager",
      "Task Manager lists running apps and processes with their CPU, memory, disk and network use, and can end "
      "a task. It also manages startup apps.",
      [("Device Manager", "Device Manager manages hardware devices and their drivers."),
       ("Event Viewer", "Event Viewer shows logs of past events; it can't end running programs."),
       ("Disk Management", "Disk Management creates and changes partitions and volumes.")],
      aliases=["Task Manager"]),
    c("device-manager", "Device Manager",
      "Which Windows tool do you use to view hardware devices and to update, roll back or disable their drivers?",
      "Device Manager",
      "Device Manager lists every hardware device, flags devices with problems, and lets you update, roll "
      "back, disable or uninstall drivers.",
      [("Task Manager", "Task Manager shows running processes and performance, not drivers."),
       ("Disk Management", "Disk Management handles partitions and volumes."),
       ("Services", "The Services console starts, stops and configures background services.")],
      aliases=["Device Manager"]),
    c("event-viewer", "Event Viewer",
      "Which Windows tool displays logs such as Application, Security and System for troubleshooting?",
      "Event Viewer",
      "Event Viewer records warnings, errors and audit events in logs, which helps you find out what happened "
      "before or during a problem.",
      [("Task Manager", "Task Manager shows what is running now, not a history of events."),
       ("Performance Monitor", "Performance Monitor tracks performance counters over time rather than event logs."),
       ("Resource Monitor", "Resource Monitor gives real-time detail on CPU, memory, disk and network use.")],
      aliases=["Event Viewer"]),
    c("disk-management", "Disk Management",
      "Which Windows utility is used to create, format, extend and shrink partitions and volumes?",
      "Disk Management",
      "Disk Management is the graphical tool for preparing drives: initializing disks, creating and formatting "
      "partitions, assigning drive letters and resizing volumes.",
      [("Device Manager", "Device Manager manages devices and drivers, not partitions."),
       ("Disk Cleanup", "Disk Cleanup frees space by removing unneeded files."),
       ("Defragment and Optimize Drives", "This tool optimizes how data is laid out on a drive; it doesn't "
                                          "create partitions.")],
      aliases=["Disk Management", "diskmgmt.msc"]),
    c("safe-mode", "Safe Mode",
      "Which Windows startup option loads only a minimal set of drivers and services to help troubleshoot "
      "problems?",
      "Safe Mode",
      "Safe Mode starts Windows with basic drivers and services only. If a problem disappears in Safe Mode, "
      "a recently added driver, startup app or service is a likely cause.",
      [("System Restore", "System Restore rolls system files and settings back to an earlier restore point."),
       ("Reset this PC", "Reset this PC reinstalls Windows."),
       ("BIOS/UEFI setup", "Firmware setup configures hardware settings before Windows starts.")],
      aliases=["Safe Mode"]),
    c("system-restore", "System Restore",
      "Which Windows feature returns system files, settings and installed programs to an earlier point without "
      "deleting personal documents?",
      "System Restore",
      "System Restore uses restore points to undo system changes, such as a bad driver or update, while leaving "
      "personal files like documents and photos alone.",
      [("File History", "File History backs up personal files; it doesn't roll back system settings."),
       ("Reset this PC", "Reset this PC reinstalls Windows, which is far more drastic."),
       ("Safe Mode", "Safe Mode is a minimal startup mode for troubleshooting; it doesn't undo changes.")],
      aliases=["System Restore", "restore point", "restore points"]),
    c("group-policy", "Group Policy",
      "Which Windows feature lets administrators centrally configure and enforce settings for domain users "
      "and computers?",
      "Group Policy",
      "Group Policy applies settings such as password rules, software restrictions and drive mappings from a "
      "central place to many users and computers in an Active Directory domain.",
      [("User Account Control (UAC)", "UAC is the elevation prompt on a single computer."),
       ("Registry Editor", "Registry Editor changes settings directly on one computer, not centrally."),
       ("Task Scheduler", "Task Scheduler runs programs or scripts at set times or events.")],
      aliases=["Group Policy", "gpedit", "gpedit.msc", "GPO"]),
    c("domain", "Windows domain",
      "Which Windows network model uses a central server, a domain controller, to manage user accounts and "
      "security policies?",
      "A domain (Active Directory)",
      "In a domain, a domain controller running Active Directory stores accounts and policies centrally, so "
      "users can sign in to any joined computer with one account.",
      [("A workgroup", "In a workgroup each computer manages its own local accounts; there is no central server."),
       ("A local account", "A local account exists only on one computer."),
       ("A VPN", "A VPN creates an encrypted connection across a network; it doesn't manage accounts.")],
      aliases=["Active Directory", "domain controller", "domain-joined", "Windows domain"], generic=["workgroup"]),
    # -------------------------------------------------------------- commands
    c("sfc", "sfc",
      "Which Windows command scans for and repairs corrupted or missing protected system files?",
      "sfc (System File Checker)",
      "Running sfc /scannow checks Windows system files against known-good copies and replaces any that are "
      "damaged or missing.",
      [("chkdsk", "chkdsk checks a disk's file system for errors and bad sectors, not Windows system files."),
       ("gpupdate", "gpupdate refreshes Group Policy settings."),
       ("diskpart", "diskpart manages disks and partitions from the command line.")],
      aliases=["sfc", "System File Checker", "sfc /scannow"]),
    c("chkdsk", "chkdsk",
      "Which Windows command checks a disk's file system for errors and can attempt to fix them?",
      "chkdsk",
      "chkdsk scans the file system for logical errors, and with /f or /r it fixes them and locates bad "
      "sectors.",
      [("sfc", "sfc repairs protected Windows system files, not file system errors."),
       ("format", "format prepares a volume and erases its data."),
       ("diskpart", "diskpart manages partitions; it doesn't check for file system errors.")],
      aliases=["chkdsk"]),
    c("ipconfig", "ipconfig",
      "Which Windows command shows a computer's IP address, subnet mask and default gateway?",
      "ipconfig",
      "ipconfig displays the IP configuration of each network adapter. ipconfig /all adds details such as DNS "
      "servers and the MAC address, and /release and /renew manage DHCP leases.",
      [("ping", "ping tests whether another device can be reached."),
       ("tracert", "tracert shows each router hop on the path to a destination."),
       ("nslookup", "nslookup queries DNS servers to resolve names.")],
      aliases=["ipconfig"]),
    c("sudo", "sudo",
      "Which Linux command runs a single command with superuser (administrator) privileges?",
      "sudo",
      "sudo runs one command with elevated rights after checking that the user is allowed to, which avoids "
      "staying signed in as root.",
      [("su", "su switches to another user account, commonly root, for the rest of the session."),
       ("chmod", "chmod changes a file's permissions."),
       ("chown", "chown changes who owns a file.")],
      aliases=["sudo"]),
    c("chmod", "chmod",
      "Which Linux command changes a file's read, write and execute permissions?",
      "chmod",
      "chmod sets the read, write and execute permissions for a file's owner, group and others, for example "
      "chmod 755 script.sh.",
      [("chown", "chown changes the file's owner, not its permissions."),
       ("sudo", "sudo runs a command with elevated privileges."),
       ("ls", "ls lists directory contents (ls -l shows permissions but doesn't change them).")],
      aliases=["chmod"]),
    # ------------------------------------------------------------- security
    c("ransomware", "Ransomware",
      "Which type of malware encrypts a user's files and demands payment to restore access?",
      "Ransomware",
      "Ransomware locks data by encrypting it and then demands a ransom for the key. Up-to-date offline "
      "backups are the main way to recover without paying.",
      [("Spyware", "Spyware secretly gathers information about the user; it doesn't lock files."),
       ("Keylogger", "A keylogger records keystrokes to capture passwords and other typed data."),
       ("Worm", "A worm spreads itself across networks; it isn't defined by holding data hostage.")],
      aliases=["ransomware"]),
    c("trojan", "Trojan",
      "Which type of malware pretends to be legitimate software to trick a user into installing it?",
      "Trojan horse",
      "A Trojan disguises itself as something useful, such as a free utility or game. Once the user runs it, "
      "it performs hidden malicious actions.",
      [("Worm", "A worm spreads on its own across a network without needing to be installed by the user."),
       ("Rootkit", "A rootkit hides deep in the operating system to conceal itself and other malware."),
       ("Ransomware", "Ransomware encrypts files and demands payment.")],
      aliases=["Trojan", "Trojans", "Trojan horse"]),
    c("worm", "Worm",
      "Which type of malware spreads across a network by itself, without needing a user to run it?",
      "Worm",
      "A worm self-replicates by exploiting vulnerabilities, moving from system to system automatically. "
      "This is why patching and firewalls are important defenses.",
      [("Virus", "A virus needs a host file and usually a user action to spread."),
       ("Trojan horse", "A Trojan relies on tricking the user into installing it."),
       ("Spyware", "Spyware focuses on secretly collecting information.")],
      aliases=["worm", "worms"]),
    c("rootkit", "Rootkit",
      "Which type of malware embeds itself deep in the operating system so it can hide from normal detection?",
      "Rootkit",
      "A rootkit modifies core parts of the OS, or even the boot process, to hide itself and other malware. "
      "Removing one often needs specialized tools or a clean reinstall.",
      [("Keylogger", "A keylogger records keystrokes; hiding deep in the OS isn't what defines it."),
       ("Adware", "Adware displays unwanted advertising."),
       ("Trojan horse", "A Trojan disguises itself as legitimate software to get installed.")],
      aliases=["rootkit", "rootkits"]),
    c("keylogger", "Keylogger",
      "Which type of malware records what a user types in order to capture passwords and other information?",
      "Keylogger",
      "A keylogger captures keystrokes and sends them to an attacker, exposing passwords, messages and card "
      "numbers. Multifactor authentication limits the damage from stolen passwords.",
      [("Ransomware", "Ransomware encrypts files and demands payment."),
       ("Worm", "A worm spreads automatically across networks."),
       ("Rootkit", "A rootkit hides itself in the OS; it isn't specifically about recording keystrokes.")],
      aliases=["keylogger", "keyloggers", "keystroke logger"]),
    c("phishing", "Phishing",
      "Which social engineering attack uses fraudulent emails or messages that appear to come from a trusted "
      "source in order to steal information?",
      "Phishing",
      "Phishing messages impersonate banks, coworkers or services to get people to click links, open "
      "attachments or reveal credentials. Checking the sender and links before acting is the key defense.",
      [("Vishing", "Vishing is the same idea carried out by voice over the phone."),
       ("Shoulder surfing", "Shoulder surfing means watching someone's screen or keyboard in person."),
       ("Tailgating", "Tailgating means following someone through a secure door.")],
      aliases=["phishing", "spear phishing", "whaling"]),
    c("tailgating", "Tailgating",
      "Which social engineering technique involves following an authorized person through a secure door "
      "without using your own credentials?",
      "Tailgating",
      "Tailgating gets an attacker physical access by walking in behind someone who badged in. Access control "
      "vestibules (mantraps) and security awareness help prevent it.",
      [("Shoulder surfing", "Shoulder surfing is watching someone enter information such as a PIN."),
       ("Phishing", "Phishing uses fraudulent messages, not physical entry."),
       ("Impersonation", "Impersonation is pretending to be someone else, such as a technician.")],
      aliases=["tailgating", "piggybacking"]),
    c("shoulder-surfing", "Shoulder surfing",
      "Which attack involves watching someone's screen or keyboard to see information such as a PIN or password?",
      "Shoulder surfing",
      "Shoulder surfing is simply observing someone directly or through a camera. Privacy screens and "
      "awareness of your surroundings help prevent it.",
      [("Phishing", "Phishing uses deceptive messages."),
       ("Tailgating", "Tailgating is following someone through a secure door."),
       ("Keylogger", "A keylogger is malware that records keystrokes, not a person watching.")],
      aliases=["shoulder surfing"]),
    c("mfa", "Multifactor authentication",
      "Which security approach requires two or more different types of factors, such as something you know and "
      "something you have, to sign in?",
      "Multifactor authentication (MFA)",
      "MFA combines different factor types (knowledge, possession, inherence/biometrics and others), so a "
      "stolen password alone isn't enough to get in.",
      [("Single sign-on (SSO)", "SSO lets one login give access to many systems; it doesn't by itself "
                                "require multiple factors."),
       ("Principle of least privilege", "Least privilege limits what users can access, not how they prove "
                                        "who they are."),
       ("Password complexity policy", "Complex passwords are still a single factor: something you know.")],
      aliases=["MFA", "multifactor", "multi-factor", "two-factor", "2FA"]),
    c("least-privilege", "Principle of least privilege",
      "Which security principle says users should get only the access they need to do their job?",
      "The principle of least privilege",
      "Least privilege limits the damage a mistake, a compromised account or malware can do, because each "
      "account can reach only what it actually needs.",
      [("Multifactor authentication", "MFA strengthens sign-in; it doesn't limit what an account can access."),
       ("Single sign-on (SSO)", "SSO is about one login for many systems."),
       ("Implicit deny", "Implicit deny blocks anything not explicitly allowed (as in firewall rules); it "
                         "doesn't decide how much access a user should be given.")],
      aliases=["least privilege"]),
    # --------------------------------------------------------------- backups
    c("incremental", "Incremental backup",
      "Which backup type copies only the data that has changed since the last backup of any type?",
      "Incremental backup",
      "Incremental backups are fast and small, but a restore needs the last full backup plus every incremental "
      "backup made since, in order.",
      [("Full backup", "A full backup copies all selected data every time."),
       ("Differential backup", "A differential copies everything changed since the last full backup, so it "
                               "grows each day until the next full."),
       ("Synthetic full backup", "A synthetic full combines existing backups into a new full backup without "
                                 "reading all the data from the source again.")],
      aliases=["incremental"]),
    c("differential", "Differential backup",
      "Which backup type copies everything that has changed since the last full backup?",
      "Differential backup",
      "A differential backup always captures every change since the last full backup, so each one grows until "
      "the next full backup. The upside is a simple restore: the last full backup plus the most recent "
      "differential.",
      [("Incremental backup", "An incremental copies only changes since the last backup of any type."),
       ("Full backup", "A full backup copies all selected data."),
       ("Snapshot", "A snapshot captures the state of a system or volume at a point in time.")],
      aliases=["differential"]),
    # -------------------------------------------------- operational procedures
    c("change-mgmt", "Change management",
      "Which formal process documents, reviews, approves and schedules changes to IT systems to reduce the risk "
      "of outages?",
      "Change management",
      "Change management requires a documented request, risk analysis, a rollback plan and approval (often by "
      "a change advisory board) before a change is made.",
      [("Incident management", "Incident management restores service after something has already gone wrong."),
       ("Asset management", "Asset management tracks hardware and software inventory."),
       ("A ticketing system", "A ticketing system tracks support requests; it isn't the approval process "
                              "for changes.")],
      aliases=["change management", "change control", "change advisory board", "change request"]),
    c("esd", "ESD protection",
      "What is the main purpose of an antistatic (ESD) wrist strap when working inside a computer?",
      "To prevent electrostatic discharge from damaging components",
      "An ESD strap keeps you at the same electrical potential as the equipment, so static built up on your "
      "body doesn't discharge into sensitive components.",
      [("To protect you from electric shock", "An ESD strap doesn't protect against high voltage; always "
                                              "disconnect power before working inside a computer."),
       ("To keep components cool", "Wrist straps have nothing to do with cooling."),
       ("To connect the computer to earth ground through the power cord", "The strap is about equalizing "
                                                                         "static charge between you and the "
                                                                         "equipment, not powering it.")],
      aliases=["ESD", "electrostatic discharge", "antistatic", "anti-static"]),
    c("sds", "Safety Data Sheet",
      "Which document gives handling, storage, disposal and first-aid information for a hazardous product such "
      "as toner?",
      "A Safety Data Sheet (SDS)",
      "Manufacturers provide an SDS (formerly MSDS) for hazardous materials, describing the risks and how to "
      "store, handle, dispose of and respond to exposure to the product.",
      [("Acceptable use policy (AUP)", "An AUP sets rules for how users may use an organization's systems."),
       ("Service-level agreement (SLA)", "An SLA defines the service levels a provider commits to."),
       ("Knowledge base article", "A knowledge base article documents how to solve a known IT issue.")],
      aliases=["SDS", "MSDS", "safety data sheet", "material safety data sheet"]),
    # ------------------------------------------------------- remote access
    c("rdp", "Remote Desktop Protocol",
      "Which Microsoft protocol gives remote graphical access to a Windows desktop and uses TCP port 3389 by "
      "default?",
      "Remote Desktop Protocol (RDP)",
      "RDP shows the remote Windows desktop and sends your keyboard and mouse input to it. Because it is a "
      "common target, it should not be exposed directly to the internet.",
      [("SSH", "SSH gives encrypted command-line access and uses TCP port 22."),
       ("VNC", "VNC is a cross-platform remote desktop tool, commonly on port 5900."),
       ("Telnet", "Telnet is unencrypted, text-based remote access on port 23.")],
      aliases=["RDP", "Remote Desktop"]),
    c("ssh", "SSH",
      "Which protocol provides encrypted command-line remote access and uses TCP port 22 by default?",
      "SSH (Secure Shell)",
      "SSH encrypts the whole session, including credentials, which makes it the secure replacement for Telnet "
      "when managing systems remotely.",
      [("Telnet", "Telnet sends everything, including passwords, unencrypted on port 23."),
       ("RDP", "RDP is graphical Windows remote access on port 3389."),
       ("FTP", "FTP transfers files and isn't a remote command shell.")],
      aliases=["SSH", "Secure Shell"]),
]

BY_KEY = {concept.key: concept for concept in CONCEPTS}
