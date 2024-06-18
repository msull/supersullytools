import gzip
import os
import subprocess
import tempfile
from enum import Enum
from io import BytesIO, IOBase
from typing import IO, ClassVar, Optional

import boto3
import matplotlib.pyplot as plt
from humanize import naturalsize
from PIL import Image, ImageDraw, ImageFont
from pydantic import ConfigDict, computed_field
from simplesingletable import DynamoDbMemory, DynamoDbResource
from smart_open import open

from supersullytools.utils.misc import date_id


class MediaType(str, Enum):
    pdf = "pdf"
    text = "text"
    image = "image"
    audio = "audio"
    archive = "archive"
    video = "video"
    document = "document"  # generic catch-all


class StoredMedia(DynamoDbResource):
    src_filename: Optional[str] = None
    media_type: MediaType
    file_size_bytes: int = None
    preview_size_bytes: int = None
    content_gzipped: bool = False

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    @computed_field
    @property
    def file_size(self) -> str:
        if self.file_size_bytes:
            return naturalsize(self.file_size_bytes)
        return ""

    @computed_field
    @property
    def preview_size(self) -> str:
        if self.preview_size_bytes:
            return naturalsize(self.preview_size_bytes)
        return ""


class MediaManager:
    VALID_MEDIA_TYPES = ["image", "video", "audio", "document", "html"]

    def __init__(self, bucket_name: str, logger, dynamodb_memory, global_prefix: str = ""):
        self.bucket_name = bucket_name
        self.logger = logger
        self.dynamodb_memory: DynamoDbMemory = dynamodb_memory
        self.global_prefix = global_prefix.rstrip("/") + "/" if global_prefix else ""

    def generate_preview(self, file_obj: IOBase, media_type: MediaType) -> bytes:
        try:
            media_type = MediaType[media_type]
        except KeyError:
            raise ValueError(f"Invalid media type: {media_type}. Valid types are: {', '.join(list(MediaType))}")

        try:
            if media_type == MediaType.image:
                return generate_image_thumbnail(file_obj)
            elif media_type == MediaType.audio:
                return generate_audio_waveform(file_obj)
            elif media_type == MediaType.video:
                return generate_video_thumbnail(file_obj)
            elif media_type == MediaType.pdf:
                return generate_pdf_preview(file_obj)
        except:  # noqa
            self.logger.exception("Error generating preview")
        return generate_no_preview_available()

    def list_available_media(self, num: int = 10, oldest_first: bool = True, pagination_key: Optional[str] = None):
        return self.dynamodb_memory.list_type_by_updated_at(
            StoredMedia, ascending=oldest_first, pagination_key=pagination_key, results_limit=num
        )

    def upload_new_media(
        self, source_file_name: str, media_type: MediaType, file_obj: IOBase, use_gzip: bool = False
    ) -> StoredMedia:
        try:
            media_type = MediaType[media_type]
        except KeyError:
            raise ValueError(f"Invalid media type: {media_type}. Valid types are: {', '.join(list(MediaType))}")

        upload_id = date_id()
        prefixed_file_name = "/".join([self.global_prefix, upload_id]).replace("//", "/")
        s3_uri = f"s3://{self.bucket_name}/{prefixed_file_name}"

        try:
            if use_gzip:
                compressed_io = BytesIO()
                with gzip.GzipFile(fileobj=compressed_io, mode="wb") as gz:
                    gz.write(file_obj.read())
                compressed_io.seek(0)
                write_obj = compressed_io
            else:
                write_obj = file_obj

            write_obj.seek(0, 2)  # Move to the end of the file to get its size
            file_size_bytes = write_obj.tell()
            write_obj.seek(0)  # Reset the file pointer to the beginning

            with open(s3_uri, "wb") as s3_file:
                s3_file.write(write_obj.read())

            self.logger.info(f"Successfully uploaded {source_file_name} to {s3_uri}")
            # Generate and upload preview
            file_obj.seek(0)
            preview_data = self.generate_preview(file_obj, media_type)
            preview_io = BytesIO(preview_data)
            preview_io.seek(0, 2)  # Move to the end of the file to get its size
            preview_size_bytes = preview_io.tell()
            preview_io.seek(0)  # Reset the file pointer to the beginning

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
                    "preview_size_bytes": preview_size_bytes,
                    "content_gzipped": use_gzip,
                },
                override_id=upload_id,
            )
            return metadata
        except Exception as e:
            self.logger.exception(f"Failed to upload {source_file_name} to {s3_uri}: {str(e)}")
            raise

    def delete_media(self, media_id: str) -> None:
        metadata = self.retrieve_metadata(media_id)  # Ensure the media exists
        prefixed_file_name = "/".join([self.global_prefix, media_id]).replace("//", "/")
        s3_uri = f"{self.bucket_name}/{prefixed_file_name}"
        preview_s3_uri = f"{s3_uri}_preview"

        s3_client = boto3.client("s3")

        try:
            # Idempotent deletion of the main file from S3
            try:
                s3_client.delete_object(Bucket=self.bucket_name, Key=prefixed_file_name)
                self.logger.info(f"Successfully deleted {s3_uri}")
            except s3_client.exceptions.ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    self.logger.info(f"{s3_uri} already deleted or does not exist")
                else:
                    raise

            # Idempotent deletion of the preview file from S3
            try:
                s3_client.delete_object(Bucket=self.bucket_name, Key=f"{prefixed_file_name}_preview")
                self.logger.info(f"Successfully deleted {preview_s3_uri}")
            except s3_client.exceptions.ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    self.logger.info(f"{preview_s3_uri} already deleted or does not exist")
                else:
                    raise

            # Delete the metadata from DynamoDB
            self.dynamodb_memory.delete_existing(metadata)
            self.logger.info(f"Successfully deleted metadata for media ID {media_id}")
        except Exception as e:
            self.logger.exception(f"Failed to delete media ID {media_id}: {str(e)}")
            raise

    def retrieve_metadata(self, media_id: str) -> StoredMedia:
        try:
            metadata = self.dynamodb_memory.read_existing(media_id, StoredMedia)
            self.logger.info(f"Successfully retrieved metadata for media ID {media_id}")
            return metadata
        except Exception as e:
            self.logger.exception(f"Failed to retrieve metadata for media ID {media_id}: {str(e)}")
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
            self.logger.exception(f"Failed to retrieve contents for media ID {media_id}: {str(e)}")
            raise

    def retrieve_media_contents(self, media_id: str) -> IO[bytes]:
        metadata = self.retrieve_metadata(media_id)
        prefixed_file_name = "/".join([self.global_prefix, media_id]).replace("//", "/")
        s3_uri = f"s3://{self.bucket_name}/{prefixed_file_name}"

        try:
            with open(s3_uri, "rb") as s3_file:
                contents = s3_file.read()

            self.logger.info(f"Successfully retrieved contents for media ID {media_id}")

            if metadata.content_gzipped:
                decompressed_io = BytesIO()
                with gzip.GzipFile(fileobj=BytesIO(contents), mode="rb") as gz:
                    decompressed_io.write(gz.read())
                decompressed_io.seek(0)
                return decompressed_io
            else:
                return BytesIO(contents)
        except Exception as e:
            self.logger.exception(f"Failed to retrieve contents for media ID {media_id}: {str(e)}")
            raise

    def retrieve_media_preview(self, media_id: str):
        prefixed_file_name = "/".join([self.global_prefix, media_id]).replace("//", "/")
        s3_uri = f"s3://{self.bucket_name}/{prefixed_file_name}_preview"

        try:
            with open(s3_uri, "rb") as s3_file:
                contents = s3_file.read()
            self.logger.info(f"Successfully retrieved preview contents for media ID {media_id}")
            return contents
        except Exception as e:
            self.logger.exception(f"Failed to retrieve preview contents for media ID {media_id}: {str(e)}")
            return generate_no_preview_available()
            # raise


def resize_image(image: Image, max_size: (int, int) = (200, 200)) -> Image:
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    return image


# Helper functions
def generate_image_thumbnail(file_obj: IOBase, size=(200, 200)) -> bytes:
    image = Image.open(file_obj)
    image.thumbnail(size)
    thumb_io = BytesIO()
    image.save(thumb_io, format=image.format)
    thumb_io.seek(0)
    return thumb_io.read()


def generate_audio_waveform(file_obj: IOBase) -> bytes:
    try:
        from pydub import AudioSegment
    except ImportError:
        return generate_no_preview_available()
    try:
        # Load the audio file
        file_obj.seek(0)
        audio = AudioSegment.from_file(file_obj)

        # Get the raw audio data as an array of samples
        samples = audio.get_array_of_samples()

        # Plot the waveform
        plt.figure(figsize=(10, 2))
        plt.plot(samples)
        plt.axis("off")

        # Save the plot to a BytesIO object
        waveform_io = BytesIO()
        plt.savefig(waveform_io, format="png")
        plt.close()
        waveform_io.seek(0)

        image = Image.open(waveform_io)
        image = resize_image(image, max_size=(200, 200))

        resized_io = BytesIO()
        image.save(resized_io, format="PNG")
        resized_io.seek(0)
        return resized_io.read()
    except Exception as e:
        raise Exception(f"Failed to generate audio waveform: {str(e)}")


def generate_pdf_preview(file_obj: IOBase) -> bytes:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return generate_no_preview_available()
    file_obj.seek(0)
    pdf = pdfium.PdfDocument(file_obj)
    page = pdf[0]
    pil_image = page.render(scale=2).to_pil()
    preview_io = BytesIO()
    pil_image.save(preview_io, format="JPEG")
    preview_io.seek(0)
    image = Image.open(preview_io)
    image = resize_image(image, max_size=(200, 200))

    resized_io = BytesIO()
    image.save(resized_io, format="PNG")
    resized_io.seek(0)
    return resized_io.read()


def generate_video_thumbnail(file_obj: IOBase) -> bytes:
    file_obj.seek(0)
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    frame_file = None
    try:
        temp_file.write(file_obj.read())
        temp_file.flush()  # Ensure all data is written to disk
        temp_file.close()

        # Verify the file is correctly written
        if not os.path.exists(temp_file.name):
            raise Exception(f"Temporary file {temp_file.name} was not created successfully.")

        # Prepare the output file for the thumbnail
        frame_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        frame_file.close()

        # Run ffmpeg to extract a frame
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", temp_file.name, "-ss", "00:00:01.000", "-vframes", "1", frame_file.name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Check if ffmpeg succeeded
        if result.returncode != 0:
            error_message = result.stderr.decode("utf-8")
            raise Exception(f"Failed to generate video thumbnail: {error_message}")

        # Load the frame and convert to bytes
        with open(frame_file.name, "rb") as img_file:
            image = Image.open(img_file)
            image = resize_image(image, max_size=(200, 200))
            thumbnail_io = BytesIO()
            image.save(thumbnail_io, format="JPEG")
            thumbnail_io.seek(0)
            return thumbnail_io.read()
    finally:
        # Cleanup temporary files
        os.remove(temp_file.name)
        if frame_file:
            os.remove(frame_file.name)


def generate_no_preview_available() -> bytes:
    # Generate a "No Preview Available" image
    width, height = 200, 200
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    text = "No Preview Available"
    try:
        # Use a TrueType font if available
        font = ImageFont.truetype("arial.ttf", 10)
    except IOError:
        # Otherwise, use the default bitmap font
        font = ImageFont.load_default()

    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    text_x = (width - text_width) / 2
    text_y = (height - text_height) / 2
    draw.text((text_x, text_y), text, fill="black", font=font)

    thumb_io = BytesIO()
    image.save(thumb_io, format="JPEG")
    thumb_io.seek(0)
    return thumb_io.read()
