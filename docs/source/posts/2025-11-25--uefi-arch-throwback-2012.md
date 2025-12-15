---
date: 2025-11-25
authors:
- the.dusktreader
comments: true
tags:
- Linux
categories:
- dev
---

# UEFI Arch (Throwback 2012)

!!! tip "Throwback"
    In 2012, I documented the process of setting up a laptop with UEFI. I read it every now and then,
    and I thought it might be interesting to others as well. Here is the unedited document copied from
    my google drive.

_Installing ArchLinux on a Notebook with UEFI_


<!-- more -->

## Introduction

In the early part of the summer of 2012, I purchased a new notebook computer. It was my first experience with
purchasing a notebook, but I had wanted one for a while and decided it was time. Sadly, I started the whole
experience in the worst way by choosing to purchase the most economical (read: cheap) notebook I could stomach.
I landed on an Acer Aspire. My choice computer included one of the relatively new AMD APU processors that combines
a GPU and CPU on a single chip. I figured that I would use this new computer mostly for working on my thesis for my
Master’s Degree in Computer Science[^1]. So, I could afford to forgo a great graphics card and most of the other
frills that come with a better system.

Being a diehard linux user, the first thing I did upon getting the new computer onto my desk at home was to slide a
Ubuntu 12.04 install disk into the system and blast all traces of Microsoft software into the oblivion such
abominations deserve. This went over well for the most part, but during the install process I noticed something sort
of fundamentally different. This was a UEFI system.

I had heard about UEFI before and knew about the great skirmish happening over Microsoft’s secure boot designs. I had
hoped to skirt such problems by sticking with BIOS based systems. Well, it was too late to back out now, and Ubuntu
had seemed to handle the install without a problem. So, no worries.

I got sick of Ubuntu and tired of Unity. It looks pretty. It works well. I like the features. But, it is a hog! I just
couldn’t stomach the slower speeds of my system, and frame-rates on my preferred game, UrbanTerror, were periodically
too low to handle.

I decided in January of 2013 to do something I’d been meaning to do for a while. I was going to re-visit Arch Linux
and start from the ground up.

That’s where things got hairy. UEFI is not a trivial obstacle to handle with a linux distro that expects the user to
manually overcome hardware configuration obstacles. This article describes the process that I used to finally get Arch
successfully installed on my system. It is not gospel. I did some things that didn’t follow the strict recommendations
of the Arch gurus on the ArchWiki or the Arch forums. But, what I ended up with worked, and that was what mattered to
me most.

This article also doesn’t document all the things that I tried and failures I had along the way. This is just a walk-
through of things that worked. The journey was in reality, much more winding and treacherous. In this article, I get to
pretend that the path was well worn and easy to follow.

[^1]: _Note from the future_: I never finished this degree.


## Resources

_It’s dangerous to go alone. Take this!_

Installing Arch is an involved process that takes more than a little patience and self-reliance. However, there are
ample resources out there that really helped me along. I’ve listed them here because, even though a simple google search
can usually fetch them easily, sometimes it’s nice to have a quick reference.

* ArchWiki:
    * Homepage: [http://wiki.archlinux.org](http://wiki.archlinux.org)
    * UEFI Article: [https://wiki.archlinux.org/index.php/Unified_Extensible_Firmware_Interface](https://wiki.archlinux.org/index.php/Unified_Extensible_Firmware_Interface)
* ArchForums:
    * Homepage: [bbs.archlinux.org](bbs.archlinux.org)
* rEFInd:
    * Homepage: [http://www.rodsbooks.com/refind/](http://www.rodsbooks.com/refind/)


## Setting up a UEFI bootable Archiso USB Installer

loren ipsum[^2]

[^2]: _Note from the future_: I wish I would have written this section. I wonder how different things are now...


## Preparing the system to install Arch

### Partitioning the HDD

Time honored tradition of linux dictates that one should set up at least 4 partitions for a new install; one partition
each for `boot`, `swap`, `root`, and `home`. This is the way I chose to set up my system. After deciding to follow
ancient wisdom, I set about partitioning my HDD.

First, I needed to check the layout of disks on my system. This was easy enough by using the fdisk command:

```shell
$ fdisk -l
<add output>
```

Looking at the output, I was able to identify my HDD by its relative size (about 500 GB). So, I noted where it appeared
in the `/dev/` tree. In this case it was `/dev/sda`

Next, I set about actually setting up the partitions. Because I wanted to have a `GPT` (GUID Partition Table)
partitioned disk, I needed to use the `gdisk` utility instead of the traditional `fdisk` utility that is usually used for
setting up `MBR` disks.

My goal was to set up 4 partitions like so:

| Dev Tree Location | FS Location | Size                | FS Type     |
|-------------------|-------------|---------------------|-------------|
| /dev/sda1         | /boot       | 1 GB                | FAT32       |
| /dev/sda2         | swap        | 1 GB                | linux-swap  |
| /dev/sda3         | /           | 20 GB               | ext4        |
| /dev/sda4         | /home       | ~478 GB (remaining) |  ext4       |

So, I ran gdisk, and iterated through the menu with the following values:

```shell
$ gdisk /dev/sda
: n,    <default> (1),    <default>,    +1G,                 ef00 (EFI system)
: n,    <default> (2),    <default>,    +1G,                 8200 (linux-swap)
: n,    <default> (3),    <default>,    +20G,                <default> (linux)
: n,    <default> (4),    <default>,    <default> (rest),    <default>
: w,    Y
```

And, just like that, my new partition table was written. Of course, anything that was on the disk had been obliterated
by writing the partition table, but that almost goes without saying. I mean, no one has lost any important data by
recklessly writing to the partition table, right?


Thanks for reading!
