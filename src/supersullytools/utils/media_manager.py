"""
media_manager.py

This module written primarily by Chat GPT:

https://chatgpt.com/share/f13a0787-4514-444c-95e3-be2daca4b042

This module provides functionality for managing media files stored in an Amazon S3 bucket,
with metadata stored in Amazon DynamoDB. It includes features for uploading, retrieving,
generating previews, and deleting media files, with optional gzip compression and encryption
support for efficient and secure storage of compressible data like CSV and JSON files.

Classes:
    MediaType: An enumeration of supported media types.
    StoredMedia: A Pydantic model representing the metadata for a stored media file.
    MediaManager: A class responsible for managing media files and their metadata.

Functions:
    resize_image(image: Image, max_size: (int, int) = (200, 200)) -> Image:
        Resizes an image to fit within the specified maximum dimensions while maintaining the aspect ratio.

    generate_image_thumbnail(file_obj: IOBase, size: (int, int) = (200, 200)) -> bytes:
        Generates a thumbnail image from the provided image file object.

    generate_audio_waveform(file_obj: IOBase) -> bytes:
        Generates a waveform image from the provided audio file object.

    generate_pdf_preview(file_obj: IOBase) -> bytes:
        Generates a preview image from the first page of the provided PDF file object.

    generate_video_thumbnail(file_obj: IOBase) -> bytes:
        Generates a thumbnail image from the provided video file object using ffmpeg.

    generate_no_preview_available() -> bytes:
        Generates a "No Preview Available" image for unsupported media types or when preview generation fails.

Dependencies:
    - boto3: For interacting with Amazon S3.
    - gzip: For gzip compression and decompression.
    - matplotlib: For generating audio waveform images.
    - PIL (Pillow): For image processing.
    - pydantic: For data validation and settings management.
    - simplesingletable: For interacting with DynamoDB.
    - smart_open: For reading and writing files from/to S3.
    - pydub: For audio file manipulation (optional).
    - pypdfium2: For PDF file manipulation (optional).
    - cryptography: For encryption and decryption of media files (optional).

Usage:
    # Initialize the MediaManager
    media_manager = MediaManager(bucket_name='your-bucket-name', logger=your_logger, dynamodb_memory=your_dynamodb_memory)

    # Upload a new media file
    with open('path/to/your/file.jpg', 'rb') as file_obj:
        media_manager.upload_new_media('file.jpg', MediaType.image, file_obj)

    # Retrieve a media file's metadata and contents
    metadata, contents = media_manager.retrieve_media_metadata_and_contents('media_id')

    # Delete a media file
    media_manager.delete_media('media_id')

Encryption:
    To use encryption features, the `cryptography` library must be installed. You can generate a Fernet key
    and use it for encryption and decryption as shown below:

    # Generate a Fernet key
    from cryptography.fernet import Fernet
    encryption_key = Fernet.generate_key()

    # Initialize the MediaManager with encryption
    media_manager = MediaManager(bucket_name='your-bucket-name', logger=your_logger, dynamodb_memory=your_dynamodb_memory)

    # Upload a new media file with encryption
    with open('path/to/your/file.jpg', 'rb') as file_obj:
        media_manager.upload_new_media('file.jpg', MediaType.image, file_obj, encryption_key=encryption_key)

    # Retrieve and decrypt a media file's contents
    metadata, contents = media_manager.retrieve_media_metadata_and_contents('media_id', encryption_key=encryption_key)

Conditional Import:
    The cryptography library is imported conditionally. If the library is not available, an ImportError will be
    raised when attempting to use encryption or decryption features.
"""

import gzip
import os
import secrets
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

try:
    # from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False


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
    file_size_bytes: int = None  # raw size of uploaded media file
    storage_size_bytes: int = None  # size of the file being sent to storage (possibly compressed / encrypted)
    preview_size_bytes: int = None  # raw size of the preview file
    preview_storage_size_bytes: int = (
        None  # size of the preview being sent to storage (possibly compressed / encrypted)
    )
    content_gzipped: bool = False
    content_encrypted: bool = False
    preview_encrypted: bool = False

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    @computed_field
    @property
    def file_size(self) -> str:
        if self.file_size_bytes:
            return naturalsize(self.file_size_bytes)
        return ""

    @computed_field
    @property
    def storage_size(self) -> str:
        if self.storage_size_bytes:
            return naturalsize(self.storage_size_bytes)
        return ""

    @computed_field
    @property
    def preview_size(self) -> str:
        if self.preview_size_bytes:
            return naturalsize(self.preview_size_bytes)
        return ""

    @computed_field
    @property
    def preview_storage_size(self) -> str:
        if self.preview_storage_size_bytes:
            return naturalsize(self.preview_storage_size_bytes)
        return ""


class MediaManager:
    """
    MediaManager is responsible for handling the upload, retrieval, preview generation,
    and deletion of media files stored in an S3 bucket, with metadata stored in DynamoDB.
    It supports optional gzip compression for efficient storage of highly compressible data.

    Attributes:
        bucket_name (str): The name of the S3 bucket where media files are stored.
        logger (logging.Logger): Logger instance for logging information and errors.
        dynamodb_memory (DynamoDbMemory): Instance for interacting with DynamoDB to store and retrieve metadata.
        global_prefix (str): A prefix that is pre-pended to the file IDs when reading/writing to S3.

    Methods:
        generate_preview(file_obj: IOBase, media_type: MediaType) -> bytes:
            Generates a preview image for the given media file based on its type.

        list_available_media(num: int = 10, oldest_first: bool = True, pagination_key: Optional[str] = None):
            Lists available media in DynamoDB, optionally paginated and sorted.

        upload_new_media(source_file_name: str, media_type: MediaType, file_obj: IOBase, use_gzip: bool = False) -> StoredMedia:
            Uploads a new media file to S3, generates a preview, and stores metadata in DynamoDB.
            Supports optional gzip compression.

        delete_media(media_id: str) -> None:
            Deletes a media file and its preview from S3 and removes the associated metadata from DynamoDB.
            Handles idempotent deletion by checking for the existence of files before attempting to delete them.

        retrieve_metadata(media_id: str) -> StoredMedia:
            Retrieves the metadata for a given media ID from DynamoDB.

        retrieve_media_metadata_and_contents(media_id: str) -> tuple[StoredMedia, IO[bytes]]:
            Retrieves both the metadata and the content of a media file from S3 and DynamoDB.

        retrieve_media_contents(media_id: str) -> IO[bytes]:
            Retrieves the content of a media file from S3. Automatically decompresses the content if it was stored using gzip.

        retrieve_media_preview(media_id: str) -> bytes:
            Retrieves the preview image of a media file from S3.
    """

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

    @staticmethod
    def _encrypt_contents(file_obj: IOBase, encryption_key: bytes) -> IOBase:
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError("cryptography library is not available. Install it to use encryption features.")

        file_obj.seek(0)
        data = file_obj.read()
        # Encrypt a message
        nonce = secrets.token_bytes(12)  # GCM mode needs 12 fresh bytes every time
        ciphertext = nonce + AESGCM(encryption_key).encrypt(nonce, data, b"")
        encrypted_io = BytesIO(ciphertext)
        encrypted_io.seek(0)
        return encrypted_io

    @staticmethod
    def _decrypt_contents(file_obj: IOBase, encryption_key: bytes) -> IOBase:
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError("cryptography library is not available. Install it to use decryption features.")

        file_obj.seek(0)
        ciphertext = file_obj.read()
        decrypted_data = AESGCM(encryption_key).decrypt(ciphertext[:12], ciphertext[12:], b"")
        decrypted_io = BytesIO(decrypted_data)
        decrypted_io.seek(0)
        return decrypted_io

    def upload_new_media(
        self,
        source_file_name: str,
        media_type: MediaType,
        file_obj: IOBase,
        use_gzip: bool = False,
        encryption_key: Optional[bytes] = None,
        encrypt_preview: bool = True,
    ) -> StoredMedia:
        try:
            media_type = MediaType[media_type]
        except KeyError:
            raise ValueError(f"Invalid media type: {media_type}. Valid types are: {', '.join(list(MediaType))}")

        upload_id = date_id()
        prefixed_file_name = "/".join([self.global_prefix, upload_id]).replace("//", "/")
        s3_uri = f"s3://{self.bucket_name}/{prefixed_file_name}"

        try:
            file_obj.seek(0, 2)  # Move to the end of the file to get its size
            raw_file_size_bytes = file_obj.tell()
            file_obj.seek(0)  # Reset the file pointer to the beginning
            if use_gzip:
                compressed_io = BytesIO()
                with gzip.GzipFile(fileobj=compressed_io, mode="wb") as gz:
                    gz.write(file_obj.read())
                compressed_io.seek(0)
                write_obj = compressed_io
            else:
                write_obj = file_obj

            encrypted = False
            if encryption_key:
                encrypted = True
                write_obj = self._encrypt_contents(write_obj, encryption_key)

            write_obj.seek(0, 2)  # Move to the end of the file to get its size
            file_size_bytes = write_obj.tell()
            write_obj.seek(0)  # Reset the file pointer to the beginning

            with open(s3_uri, "wb") as s3_file:
                s3_file.write(write_obj.read())

            self.logger.info(f"Successfully uploaded {source_file_name} to {s3_uri}")
            # Generate and upload preview
            file_obj.seek(0)
            preview_io = BytesIO(self.generate_preview(file_obj, media_type))
            preview_io.seek(0, 2)  # Move to the end of the file to get its size
            raw_preview_size_bytes = preview_io.tell()
            preview_io.seek(0)  # Reset the file pointer to the beginning

            preview_encrypted = False
            if encryption_key and encrypt_preview:
                preview_encrypted = True
                preview_io = self._encrypt_contents(preview_io, encryption_key)

            preview_io.seek(0, 2)  # Move to the end of the file to get its size
            preview_file_size_bytes = preview_io.tell()
            preview_io.seek(0)  # Reset the file pointer to the beginning

            preview_s3_uri = f"{s3_uri}_preview"
            with open(preview_s3_uri, "wb") as s3_preview_file:
                s3_preview_file.write(preview_io.read())

            self.logger.info(f"Successfully uploaded preview for {source_file_name} to {preview_s3_uri}")

            # Create and store the media metadata
            metadata = self.dynamodb_memory.create_new(
                StoredMedia,
                {
                    "src_filename": source_file_name,
                    "media_type": media_type,
                    "file_size_bytes": raw_file_size_bytes,
                    "storage_size_bytes": file_size_bytes,
                    "preview_size_bytes": raw_preview_size_bytes,
                    "preview_storage_size_bytes": preview_file_size_bytes,
                    "content_gzipped": use_gzip,
                    "content_encrypted": encrypted,
                    "preview_encrypted": preview_encrypted,
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

    def retrieve_media_metadata_and_contents(
        self, media_id: str, encryption_key: Optional[bytes] = None
    ) -> tuple[StoredMedia, IO[bytes]]:
        metadata = self.retrieve_metadata(media_id)
        contents = self.retrieve_media_contents(media_id, encryption_key, metadata=metadata)
        return metadata, contents

    def retrieve_media_contents(
        self, media_id: str, encryption_key: Optional[bytes] = None, metadata: Optional[StoredMedia] = None
    ) -> IO[bytes]:
        metadata = metadata or self.retrieve_metadata(media_id)
        prefixed_file_name = "/".join([self.global_prefix, media_id]).replace("//", "/")
        s3_uri = f"s3://{self.bucket_name}/{prefixed_file_name}"

        if metadata.content_encrypted and not encryption_key:
            raise ValueError("Content encrypted; must supply encryption key")

        try:
            with open(s3_uri, "rb") as s3_file:
                contents = s3_file.read()

            self.logger.info(f"Successfully retrieved contents for media ID {media_id}")

            output_data = BytesIO(contents)

            if metadata.content_encrypted:
                output_data = self._decrypt_contents(file_obj=output_data, encryption_key=encryption_key)

            if metadata.content_gzipped:
                decompressed_io = BytesIO()
                with gzip.GzipFile(fileobj=output_data, mode="rb") as gz:
                    decompressed_io.write(gz.read())
                decompressed_io.seek(0)
                output_data = decompressed_io

            return output_data

        except Exception as e:
            self.logger.exception(f"Failed to retrieve contents for media ID {media_id}: {str(e)}")
            raise

    def retrieve_media_preview(self, media_id: str, encryption_key: Optional[bytes] = None):
        # note: for speed, we do not pull the metadata and check if the preview is encrypted and
        # raise an error if the key isn't supplied (which is done when retrieving contents)
        # if the preview is encrypted and no key is supplied, the preview image will just be busted
        prefixed_file_name = "/".join([self.global_prefix, media_id]).replace("//", "/")
        s3_uri = f"s3://{self.bucket_name}/{prefixed_file_name}_preview"

        try:
            with open(s3_uri, "rb") as s3_file:
                contents = s3_file.read()
            self.logger.info(f"Successfully retrieved preview contents for media ID {media_id}")
            if encryption_key:
                contents = self._decrypt_contents(file_obj=BytesIO(contents), encryption_key=encryption_key).read()
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
        from pydub.exceptions import CouldntDecodeError
    except ImportError:
        return generate_no_preview_available()
    try:
        # Load the audio file
        file_obj.seek(0)
        try:
            audio = AudioSegment.from_file(file_obj)
        except CouldntDecodeError as e:
            if "pcm_s4le" in str(e):
                audio = AudioSegment.from_file(file_obj, format="wav", codec="pcm_s16le")
            else:
                raise

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
    image = resize_image(image, max_size=(300, 300))

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
    return generate_text_image("No Preview Available")


def generate_text_image(text: str, width=200, height=200, font_size=10) -> bytes:
    # Generate a "No Preview Available" image
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    try:
        # Use a TrueType font if available
        font = ImageFont.truetype("arial.ttf", size=font_size)
    except IOError:
        # Otherwise, use the default bitmap font
        font = ImageFont.load_default(size=font_size)

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
