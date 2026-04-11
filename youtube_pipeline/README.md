# Youtube Channel Downloader

This script efficiently downloads all videos and their Chinese/English transcripts from the "老厉害" YouTube channel.

It is designed to be **intelligent and economical**:
- It **will not re-download** any videos you already have in your `youtube_downloads` directory.
- It keeps track of downloaded videos in an archive file (`youtube_downloads/download_archive.txt`), so you can run it multiple times, and it will only fetch new content.

## How to Use

I have already created the script and made it executable for you. To start downloading all missing videos and transcripts, simply run the following command in your terminal:

```bash
./scripts/download_youtube_channel.sh
```

The script will handle the rest, placing new videos and their `.vtt` transcript files into the `./youtube_downloads/老厉害/` directory, named neatly with the upload date.
