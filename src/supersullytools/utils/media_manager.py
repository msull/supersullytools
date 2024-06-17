import subprocess
import tempfile
from enum import Enum
from io import IOBase, BytesIO
from typing import Optional, ClassVar

import matplotlib.pyplot as plt
import pypdfium2 as pdfium
from PIL import Image
from pydantic import computed_field, ConfigDict
from pydub import AudioSegment
from simplesingletable import DynamoDbResource
from smart_open import open
from humanize import naturalsize
from typing.io import IO

from supersullytools.utils.misc import date_id


class MediaType(str, Enum):
    document = "document"
    image = "image"
    video = "video"
    audio = "audio"
    archive = "archive"


class StoredMedia(DynamoDbResource):
    src_filename: Optional[str] = None
    media_type: MediaType
    file_size_bytes: int = None

    preview_size_bytes: int = None

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    @computed_field
    @property
    def file_size(self) -> str:
        if not self.file_size_bytes:
            return ""
        return naturalsize(self.file_size_bytes)

    @computed_field
    @property
    def preview_size(self) -> str:
        if not self.preview_size_bytes:
            return ""
        return naturalsize(self.preview_size_bytes)


class MediaManager:
    VALID_MEDIA_TYPES = ["image", "video", "audio", "document"]

    def __init__(self, bucket_name: str, logger, dynamodb_memory, global_prefix: str = ""):
        self.bucket_name = bucket_name
        self.logger = logger
        self.dynamodb_memory = dynamodb_memory
        self.global_prefix = global_prefix.rstrip("/") + "/" if global_prefix else ""

    def generate_preview(self, file_obj: IOBase, media_type: str) -> bytes:
        if media_type == "image":
            return generate_image_thumbnail(file_obj)
        elif media_type == "audio":
            return generate_audio_waveform(file_obj)
        elif media_type == "video":
            return generate_video_thumbnail(file_obj)
        elif media_type == "document":
            return generate_document_preview(file_obj)
        else:
            raise ValueError(f"Unsupported media type for preview generation: {media_type}")

    def upload_new_media(self, source_file_name: str, media_type: str, file_obj: IOBase) -> StoredMedia:
        if media_type not in self.VALID_MEDIA_TYPES:
            raise ValueError(f"Invalid media type: {media_type}. Valid types are: {', '.join(self.VALID_MEDIA_TYPES)}")

        upload_id = date_id()

        prefixed_file_name = "/".join([self.global_prefix, upload_id]).replace("//", "/")
        s3_uri = f"s3://{self.bucket_name}/{prefixed_file_name}"

        try:
            file_obj.seek(0, 2)  # Move to the end of the file to get its size
            file_size_bytes = file_obj.tell()
            file_obj.seek(0)  # Reset the file pointer to the beginning

            with open(s3_uri, "wb") as s3_file:
                s3_file.write(file_obj.read())

            self.logger.info(f"Successfully uploaded {source_file_name} to {s3_uri}")

            # Generate and upload preview
            file_obj.seek(0)
            preview_data = self.generate_preview(file_obj, media_type)
            preview_s3_uri = f"{s3_uri}_preview"
            with open(preview_s3_uri, "wb") as s3_preview_file:
                s3_preview_file.write(preview_data)

            self.logger.info(f"Successfully uploaded preview for {source_file_name} to {preview_s3_uri}")

            # Create and store the media metadata
            metadata = self.dynamodb_memory.create_new(
                StoredMedia,
                {
                    "src_filename": source_file_name,
                    "media_type": media_type,
                    "file_size_bytes": file_size_bytes,
                },
                override_id=upload_id,
            )
            return metadata
        except Exception as e:
            self.logger.error(f"Failed to upload {source_file_name} to {s3_uri}: {str(e)}")
            raise

    def retrieve_metadata(self, media_id: str) -> StoredMedia:
        try:
            metadata = self.dynamodb_memory.read_existing(media_id, StoredMedia)
            self.logger.info(f"Successfully retrieved metadata for media ID {media_id}")
            return metadata
        except Exception as e:
            self.logger.error(f"Failed to retrieve metadata for media ID {media_id}: {str(e)}")
            raise

    def retrieve_media_metadata_and_contents(self, media_id: str) -> tuple[StoredMedia, IO[bytes]]:
        metadata = self.retrieve_metadata(media_id)  # ensure exists
        prefixed_file_name = "/".join([self.global_prefix, media_id]).replace("//", "/")
        s3_uri = f"s3://{self.bucket_name}/{prefixed_file_name}"

        try:
            with open(s3_uri, "rb") as s3_file:
                contents = s3_file.read()
            self.logger.info(f"Successfully retrieved contents for media ID {media_id}")
            return metadata, contents
        except Exception as e:
            self.logger.error(f"Failed to retrieve contents for media ID {media_id}: {str(e)}")
            raise

    def retrieve_media_contents(self, media_id: str) -> IO[bytes]:
        self.retrieve_metadata(media_id)  # ensure exists
        prefixed_file_name = "/".join([self.global_prefix, media_id]).replace("//", "/")
        s3_uri = f"s3://{self.bucket_name}/{prefixed_file_name}"

        try:
            with open(s3_uri, "rb") as s3_file:
                contents = s3_file.read()
            self.logger.info(f"Successfully retrieved contents for media ID {media_id}")
            return contents
        except Exception as e:
            self.logger.error(f"Failed to retrieve contents for media ID {media_id}: {str(e)}")
            raise

    def retrieve_media_preview(self, media_id: str):
        self.retrieve_metadata(media_id)  # ensure exists
        prefixed_file_name = "/".join([self.global_prefix, media_id]).replace("//", "/")
        s3_uri = f"s3://{self.bucket_name}/{prefixed_file_name}_preview"

        try:
            with open(s3_uri, "rb") as s3_file:
                contents = s3_file.read()
            self.logger.info(f"Successfully retrieved preview contents for media ID {media_id}")
            return contents
        except Exception as e:
            self.logger.error(f"Failed to preview retrieve contents for media ID {media_id}: {str(e)}")
            raise


# Helper functions
def generate_image_thumbnail(file_obj: IOBase, size=(128, 128)) -> bytes:
    image = Image.open(file_obj)
    image.thumbnail(size)
    thumb_io = BytesIO()
    image.save(thumb_io, format=image.format)
    thumb_io.seek(0)
    return thumb_io.read()


def generate_audio_waveform(file_obj: IOBase) -> bytes:
    audio = AudioSegment.from_file(file_obj)
    samples = audio.get_array_of_samples()

    plt.figure(figsize=(10, 2))
    plt.plot(samples)
    plt.axis("off")
    waveform_io = BytesIO()
    plt.savefig(waveform_io, format="png")
    plt.close()
    waveform_io.seek(0)
    return waveform_io.read()


def generate_document_preview(file_obj: IOBase) -> bytes:
    pdf = pdfium.PdfDocument(file_obj)
    page = pdf[0]
    pil_image = page.render(scale=2).to_pil()
    preview_io = BytesIO()
    pil_image.save(preview_io, format="JPEG")
    preview_io.seek(0)
    return preview_io.read()


def generate_video_thumbnail(file_obj: IOBase) -> bytes:
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.write(file_obj.read())
    temp_file.close()

    # Extract a frame using ffmpeg (ensure ffmpeg is installed and in the PATH)
    frame_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    frame_file.close()
    subprocess.run(
        ["ffmpeg", "-i", temp_file.name, "-ss", "00:00:01.000", "-vframes", "1", frame_file.name], check=True
    )

    # Load the frame and convert to bytes
    image = Image.open(frame_file.name)
    thumbnail_io = BytesIO()
    image.save(thumbnail_io, format="JPEG")
    thumbnail_io.seek(0)
    return thumbnail_io.read()
