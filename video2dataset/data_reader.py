"""classes and functions for downloading videos"""
import os
import uuid
import requests
import yt_dlp
import io
import xmltodict
import ffmpeg
from typing import List


def video2audio(video, af, sample_rate, tmp_dir):
    """extract audio from video"""

    path = f"{tmp_dir}/{str(uuid.uuid4())}.{af}"
    num_streams = len(ffmpeg.probe(video)["streams"])
    ffmpeg_args = {"ar": str(sample_rate), "f": af} if sample_rate else {"f": af}

    if int(num_streams) > 1:  # video has audio stream
        try:
            video = ffmpeg.input(video)
            (ffmpeg.output(video.audio, path, **ffmpeg_args).run(capture_stderr=True))
        except ffmpeg.Error as e:
            print(e.stderr)
            raise e
    else:
        path = None
    return path


def sub_to_dict(sub) -> List[dict]:
    """Convert TTML to JSON"""

    captions = xmltodict.parse(sub)
    dicts = []  # type: List[dict]
    prev_s = None
    prev_text = None
    for c in captions["tt"]["body"]["div"]["p"]:
        s = c["@begin"]
        if prev_s:
            dicts.append({"start": prev_s, "end": s, "line": prev_text})

        prev_s = s
        prev_text = c["#text"]

    return dicts


def get_yt_meta(url, yt_metadata_args: dict) -> dict:
    """Return yt meta dict with meta data and/or subtitles
    yt_metadata_args is a dict of follwing format:
    yt_metadata_args = {
        'writesubtitles': True,
        'subtitleslangs': ['en'],
        'writeautomaticsub': True,
        'get_info': True
    }

    writesubtitles:    Whether to write subtitles
    writeautomaticsub: Write the automatically generated subtitles to a file
    subtitleslangs:    List of languages of the subtitles to download.
    get_info: whether to add info (title, description, tags etc) to the output.

    """

    write_subs = yt_metadata_args.get("writesubtitles", None)

    yt_metadata_args["skip_download"] = True
    yt_metadata_args["ignoreerrors"] = True
    yt_metadata_args["quiet"] = True
    yt_metadata_args["subtitlesformat"] = "ttml"

    info_dict, sub_dict = None, None

    with yt_dlp.YoutubeDL(yt_metadata_args) as yt:

        info_dict = yt.extract_info(url, download=False)
        if write_subs:
            sub_url = info_dict["requested_subtitles"][yt_metadata_args["subtitleslangs"][0]]["url"]
            res = requests.get(sub_url)
            sub = io.TextIOWrapper(io.BytesIO(res.content)).read()
            sub_dict = sub_to_dict(sub)

        if yt_metadata_args["get_info"]:
            info_dict.pop("subtitles")
            info_dict.pop("requested_formats")
            info_dict.pop("formats")
            info_dict.pop("thumbnails")
            info_dict.pop("automatic_captions")
        else:
            info_dict = None

        yt_meta_dict = {"info": info_dict, "subtitles": sub_dict}
        yt_meta_dict["split_subs"] = yt_metadata_args.get("split_subs", None)

        return yt_meta_dict


class Mp4Downloader:
    """Downloader class for mp4 links"""

    def __init__(self, timeout, tmp_dir, encode_formats):
        self.timeout = timeout
        self.tmp_dir = tmp_dir
        self.encode_formats = encode_formats
        self.sample_rate = encode_formats.get("sample_rate", None) if self.encode_formats else None

    def __call__(self, url):
        resp = requests.get(url, stream=True, timeout=self.timeout)
        vf = self.encode_formats.get("video", "mp4")
        video_path = f"{self.tmp_dir}/{str(uuid.uuid4())}.{vf}"
        with open(video_path, "wb") as f:
            f.write(resp.content)
        audio_path = None
        if self.encode_formats.get("audio", None):
            af = self.encode_formats["audio"]
            audio_path = video2audio(video_path, af, self.sample_rate, self.tmp_dir)

        if not self.encode_formats.get("video", None):
            os.remove(video_path)
            video_path = None

        return video_path, audio_path, None


class YtDlpDownloader:
    """Downloader class for yt-dlp links"""

    # TODO: maybe we just include height and width in the metadata_args
    def __init__(self, tmp_dir, metadata_args, video_size, encode_formats):
        self.tmp_dir = tmp_dir
        self.metadata_args = metadata_args
        self.video_size = video_size
        self.encode_formats = encode_formats
        if self.encode_formats:
            self.sample_rate = encode_formats.get("sample_rate", None)

    def __call__(self, url):
        audio_path = None
        path = None

        # format_string = f"bv*[height<={self.video_size}][ext=mp4]/b[height<={self.video_size}][ext=mp4] / wv/w[ext=mp4]"
        format_string = f"wv*[height>={self.video_size}][ext=mp4]/w[height>={self.video_size}][ext=mp4] / bv/b[ext=mp4]"
        audio_fmt_string = "ba[ext=m4a]"
        if self.encode_formats and self.encode_formats.get("audio", None):
            audio_path_m4a = f"{self.tmp_dir}/{str(uuid.uuid4())}.m4a"
            ydl_opts = {
                "outtmpl": audio_path_m4a,
                "format": audio_fmt_string,
                "quiet": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download(url)
            af = self.encode_formats["audio"]
            ffmpeg_args = {"ar": str(self.sample_rate), "f": af} if self.sample_rate else {"f": af}
            try:
                audio = ffmpeg.input(audio_path_m4a)
                (
                    ffmpeg.output(
                        audio, audio_path_m4a.replace(".m4a", f".{self.encode_formats['audio']}"), **ffmpeg_args
                    ).run(capture_stderr=True)
                )
                audio_path = audio_path_m4a.replace(".m4a", f".{self.encode_formats['audio']}")
            except ffmpeg.Error as e:
                print(e.stderr)
                raise e

        if self.encode_formats and self.encode_formats.get("video", None):
            path = f"{self.tmp_dir}/{str(uuid.uuid4())}.mp4"
            ydl_opts = {
                "outtmpl": path,
                "format": format_string,
                "quiet": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download(url)

        if self.metadata_args:
            yt_meta_dict = get_yt_meta(url, self.metadata_args)
        else:
            yt_meta_dict = None
        return path, audio_path, yt_meta_dict, None


class VideoDataReader:
    """Video data reader provide data for a video"""

    def __init__(self, video_size, dl_timeout, tmp_dir, yt_meta_args, encode_formats) -> None:
        self.mp4_downloader = Mp4Downloader(dl_timeout, tmp_dir, encode_formats)
        self.yt_downloader = YtDlpDownloader(tmp_dir, yt_meta_args, video_size, encode_formats)

    def __call__(self, row):
        key, url = row

        yt_meta_dict = None
        a_file_path = None
        aud_bytes = None
        vid_bytes = None
        # TODO: make nice function to detect what type of link we're dealing with
        if "youtube" in url:  # youtube link
            try:
                file_path, a_file_path, yt_meta_dict, error_message = self.yt_downloader(url)
            except Exception as e:  # pylint: disable=(broad-except)
                file_path, a_file_path, yt_meta_dict, error_message = None, None, None, str(e)
        # TODO: add .avi, .webm, should also work
        elif url.endswith(".mp4"):  # mp4 link
            file_path, a_file_path, error_message = self.mp4_downloader(url)
        else:
            file_path, a_file_path, error_message = None, None, "Warning: Unsupported URL type"

        if error_message is None:
            if file_path is not None:
                with open(file_path, "rb") as vid_file:
                    vid_bytes = vid_file.read()
            if a_file_path is not None:
                with open(a_file_path, "rb") as aud_file:
                    aud_bytes = aud_file.read()
        else:
            vid_bytes = None
        if file_path is not None:  # manually remove tempfile
            os.remove(file_path)

        streams = {"video": vid_bytes, "audio": aud_bytes}
        return key, streams, yt_meta_dict, error_message
