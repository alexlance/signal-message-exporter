# signal-message-exporter

Take a Signal encrypted backup file, decrypt it and export its contents to an
XML file that can be used with SyncTech's *SMS Backup & Restore* Android app.

This project will export all SMS + MMS + Signal messages, so that all the
messages can be re-imported into the Android messaging store.


## Caveats

 * Tested on Docker, Linux and for Android
 * Also tested on macos, if you get Error 137, you may need to bump up memory and swap in docker's settings


## Instructions

1. Generate a Signal backup file

```
Signal -> Chats -> Backups -> Local Backup
```

2. Transfer that file to your computer, file will be named eg: signal-2022-06-10-17-00-00.backup

3. Download this repo and run:

```
cd signal-message-exporter
export SIG_KEY=123451234512345123451234512345
export SIG_FILE=signal-2022-06-10-17-00-00.backup
make run
```

4. A new XML file should be generated, transfer the XML file back to your phone.

5. Run SyncTech's *SMS Backup & Restore* to import the XML file.

6. Check to see if all your messages imported into Android ok. If not, create a PR which fixes the problem ;)


## Windows instructions

I haven't tested this on Windows, but user @jbaker6953 has supplied some Windows instructions in
https://github.com/alexlance/signal-message-exporter/issues/10

and there's a reddit comment here that goes into it:
https://old.reddit.com/r/signal/comments/y7d3gj/having_trouble_with_smsmms_export_the_devs_want/iutmwr7/


## Thoughts
* Feel free to shout out with any issues problems in github issues
* Make sure to go and give signalbackup-tools some kudos as they do most of the heavy lifting
