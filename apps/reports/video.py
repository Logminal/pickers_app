import logging
import os
import shutil
import subprocess
import tempfile
import threading

from django.conf import settings
from django.core.files import File

logger = logging.getLogger(__name__)


def _run_ffmpeg(source_path, target_path):
    ffmpeg_bin = getattr(settings, 'FFMPEG_BINARY', 'ffmpeg')
    cmd = [
        ffmpeg_bin, '-y', '-i', source_path,
        '-vf', "scale='-2:min(720,ih)'",
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26',
        '-c:a', 'aac', '-b:a', '96k',
        '-movflags', '+faststart',
        target_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)


def compress_photo_report_video(report_id):
    """Пережимает видеоотчёт в H.264/AAC mp4 высотой до 720px — уменьшает размер файла,
    чтобы менеджеру было быстрее его открыть, и экономит место на диске. Если ffmpeg
    недоступен, падает или не даёт выигрыша в размере — молча оставляем исходный файл:
    это только оптимизация, а не обязательное условие работы отчёта."""
    from .models import PhotoReport

    ffmpeg_bin = getattr(settings, 'FFMPEG_BINARY', 'ffmpeg')
    if not shutil.which(ffmpeg_bin):
        logger.info('ffmpeg не найден (%s) — сжатие видеоотчёта пропущено (report_id=%s)', ffmpeg_bin, report_id)
        return

    try:
        report = PhotoReport.objects.get(pk=report_id)
    except PhotoReport.DoesNotExist:
        return
    if not report.video:
        return

    source_path = report.video.path
    with tempfile.TemporaryDirectory() as tmp_dir:
        target_path = os.path.join(tmp_dir, 'compressed.mp4')
        try:
            _run_ffmpeg(source_path, target_path)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            logger.warning('Не удалось сжать видеоотчёт (report_id=%s): %s', report_id, exc)
            return

        if not os.path.exists(target_path):
            return

        compressed_size = os.path.getsize(target_path)
        original_size = os.path.getsize(source_path)
        if compressed_size <= 0 or compressed_size >= original_size:
            logger.info('Сжатое видео не меньше исходного — оставляем оригинал (report_id=%s)', report_id)
            return

        old_name = report.video.name
        with open(target_path, 'rb') as fh:
            report.video.save('compressed.mp4', File(fh), save=False)
        report.save(update_fields=['video'])
        report.video.storage.delete(old_name)


def compress_photo_report_video_async(report_id):
    if not getattr(settings, 'VIDEO_COMPRESSION_ASYNC', True):
        compress_photo_report_video(report_id)
        return
    threading.Thread(target=compress_photo_report_video, args=(report_id,), daemon=True).start()
