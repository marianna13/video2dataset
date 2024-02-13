"""
frame subsampler adjusts the fps of the videos to some constant value
"""


import tempfile
import os
from subprocess import Popen, PIPE


class KeyframeSubsampler:
    """
    Extracts keyframes from a video.
    Args:
        sample_rate (int): Target sample rate of the audio.
        encode_format (str): Format to encode in (i.e. m4a)
    """

    def __init__(self, encode_format={"video":"jpeg"}):
        # self.sample_rate = sample_rate
        self.encode_formats = encode_format
        self.magic_str = b'\xff\xd8\xff\xe0\x00\x10JFIF'
        # self.n_audio_channels = n_audio_channels

    def __call__(self, streams, metadata=None):
        video_bytes = streams["video"]

        cmd = f"ffmpeg -skip_frame nokey -i pipe: -f image2pipe pipe:1"

        subsampled_bytes = []
        for vid_bytes in video_bytes:

            p = Popen(cmd.split(), stdin=PIPE, stdout=PIPE, stderr=PIPE)
    
            # ext = self.encode_format
            try:
                output, err = p.communicate(vid_bytes)
                frames = output.split(self.magic_str)[1:] # fisrt element is empty
                subsampled_bytes.append(list(map(lambda f: self.magic_str + f, frames)))
                print(len(frames))
                print(err)
            except Exception as err:  # pylint: disable=broad-except
                return [], None, str(err)

            # with open(f"{tmpdir}/output.{ext}", "rb") as f:
            #     subsampled_bytes.append(f.read())
        streams["video"] = subsampled_bytes
        return streams, metadata, None
