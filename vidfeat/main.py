import imfeat
import pyffmpeg
import subprocess
import Image
import re
import StringIO


def _read_fps(stderr):
    """Read the fps from FFMpeg's debug output
    """
    # Stream #0.0: Video: mpeg4, yuv420p, 1280x720 \
    # [PAR 1:1 DAR 16:9], 29.97 fps, 29.97 tbr, 29.97 tbn, 30k tbc
    while 1:
        line = stderr.readline()
        m = re.search(' Stream #.* ([\.\d]+) fps, .*', line)
        if m is None:
            continue
        return float(m.groups()[0])


def _read_ppm(fp):
    """Read one PPM image at a from a stream (ffmpeg image2pipe output)
    """
    buf = ''
    format = fp.readline()
    if not format:
        return None

    # P6
    buf += format
    size = fp.readline()
    buf += size

    # 320 240
    x,y = map(int, re.match('(\d+)\s+(\d+)', size).groups())

    # 255
    maxcol = fp.readline()
    buf += maxcol

    # <rgb data>
    data = fp.read(x*y*3)
    buf += data

    frame = Image.open(StringIO.StringIO(buf))
    return frame


def convert_video_ffmpeg(file_name, image_modes):
    """
    Args:
        filename: video file to open
        modes: List of valid video types

    Returns:
        Valid image

    Raises:
        ValueError: There was a problem converting the color.
    """
    def _frame_iter(file_name, image_modes):
        stream = pyffmpeg.VideoStream()
        stream.open(file_name)
        return frame_iter(stream, image_modes)

    if image_modes[0] == 'videostream':
        return _frame_iter(file_name, image_modes)

    elif not image_modes[0] == 'frameiter':
        raise ValueError('Unknown image type')

    try:
        proc = subprocess.Popen('ffmpeg -i %s -f image2pipe -vcodec ppm -' % file_name,
                                stdout=subprocess.PIPE,
                                stdin=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                close_fds=True, shell=True)
    except ValueError, e:
        print e
        # Fall back to the other iterator if ffmpeg is not found
        return _frame_iter(file_name, image_modes)

    # Get the FPS from the ffmpeg stderr dump
    fps = _read_fps(proc.stderr)

    def gen():
        try:
            frame_num = 0
            while True:
                frame = _read_ppm(proc.stdout)
                if frame is None:
                    break
                yield frame_num, frame_num / fps, frame
                frame_num += 1
        finally:
            proc.kill()
            proc.wait()

    return gen()


def frame_iter(stream, image_modes, mod=1):
    SEEK_START_ATTEMPTS = 3
    # Use seek to find the first good frame
    for i in range(SEEK_START_ATTEMPTS):
        try:
            stream.tv.seek_to_frame(i)
        except IOError:
            continue
        else:
            break
    fps = stream.tv.get_fps()
    cnt = 0
    while 1:
        if cnt % mod == 0:
            _, num, frame = stream.tv.get_current_frame()[:3]
            yield num, num / fps, imfeat.convert_image(frame, image_modes)
        try:
            stream.tv.get_next_frame()
        except IOError:
            break
        cnt += 1


def convert_video(video, modes):
    """
    Args:
        image: A pyffmpeg.VideoStream video object
        modes: List of valid video types

    Returns:
        Valid image

    Raises:
        ValueError: There was a problem converting the color.
    """
    if isinstance(video, pyffmpeg.VideoStream):
        if modes[0] == 'videostream':
            return video
        elif modes[0] == 'frameiter':
            return frame_iter(video, modes[1])
        elif modes[0] == 'frameiterskip':
            return frame_iter(video, modes[1], modes[2])
    else:
        raise ValueError('Unknown image type')
